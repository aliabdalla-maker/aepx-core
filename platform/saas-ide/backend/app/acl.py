"""Server-side permission matrix (spec §5): default deny, least privilege, per role and resource.

The UI may hide controls, but every mutating endpoint calls require() and the database still
enforces tenant row-level security underneath. Unknown roles, actions or resources are denied.
"""
from fastapi import HTTPException

ROLES = ("owner", "admin", "editor", "media_editor", "reviewer", "viewer", "agent")
ACTIONS = ("view", "create", "edit", "delete", "execute_agent", "approve", "publish", "manage_members")

# Paths a media editor may change: the media folders every module creates.
MEDIA_PREFIXES = ("media/", "assets/", "audio/", "music/", "video/", "film/", "animation/", "social/")

ALL = "all"
MEDIA = "media"
_MATRIX: dict[str, dict[str, str]] = {
    # Tenant administrator / project owner: everything; publishing still goes through HITL approval.
    "owner": {a: ALL for a in ACTIONS},
    "admin": {a: ALL for a in ACTIONS},
    # Developer: builds and runs agents; may delete files but not projects; no approvals or publishing.
    "editor": {"view": ALL, "create": ALL, "edit": ALL, "delete": "files", "execute_agent": ALL},
    # Media editor: assigned media assets only.
    "media_editor": {"view": ALL, "create": MEDIA, "edit": MEDIA, "delete": MEDIA, "execute_agent": ALL},
    # Reviewer: reads and approves; never edits, deletes or executes.
    "reviewer": {"view": ALL, "approve": ALL},
    "viewer": {"view": ALL},
    # AI agents: scoped reads and proposals; deletion and publishing denied by default.
    "agent": {"view": ALL, "create": "files", "edit": "files"},
}


def is_media_path(path: str | None) -> bool:
    return bool(path) and any(path.startswith(p) for p in MEDIA_PREFIXES)


def allowed(role: str, action: str, resource: str = "project", path: str | None = None) -> bool:
    scope = _MATRIX.get(role, {}).get(action)
    if scope is None or action not in ACTIONS:
        return False
    if scope == ALL:
        return True
    if scope == "files":
        return resource == "file"
    if scope == MEDIA:
        return resource == "file" and is_media_path(path)
    return False


def require(role: str, action: str, resource: str = "project", path: str | None = None) -> None:
    if not allowed(role, action, resource, path):
        raise HTTPException(403, f"Role '{role}' may not {action.replace('_', ' ')} this {resource}")


def matrix() -> dict:
    """Readable matrix for the UI and audits: role -> action -> scope ('all', 'files', 'media', 'none')."""
    return {r: {a: _MATRIX[r].get(a, "none") for a in ACTIONS} for r in ROLES}
