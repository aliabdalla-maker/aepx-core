"""Unit tests: ACL permission matrix (spec §5) and IDE module registry (spec §2-4)."""
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import acl, modules


@pytest.mark.parametrize("role,action,resource,path,expected", [
    ("owner", "publish", "project", None, True),
    ("admin", "manage_members", "workspace", None, True),
    ("editor", "edit", "file", "src/app.py", True),
    ("editor", "delete", "file", "src/app.py", True),
    ("editor", "delete", "project", None, False),
    ("editor", "approve", "run", None, False),
    ("editor", "publish", "project", None, False),
    ("media_editor", "edit", "file", "audio/mix.json", True),
    ("media_editor", "edit", "file", "src/app.py", False),
    ("media_editor", "delete", "file", "film/script.fountain", True),
    ("media_editor", "create", "project", None, False),
    ("reviewer", "approve", "run", None, True),
    ("reviewer", "edit", "file", "media/x.json", False),
    ("reviewer", "execute_agent", "run", None, False),
    ("viewer", "view", "project", None, True),
    ("viewer", "edit", "file", "media/x", False),
    ("agent", "edit", "file", "src/x.py", True),
    ("agent", "delete", "file", "src/x.py", False),
    ("agent", "publish", "project", None, False),
    ("unknown", "view", "project", None, False),
    ("owner", "launch_missiles", "project", None, False),
])
def test_matrix_is_default_deny_and_least_privilege(role, action, resource, path, expected):
    assert acl.allowed(role, action, resource, path) is expected


def test_require_raises_403_and_matrix_is_complete():
    with pytest.raises(HTTPException) as err:
        acl.require("viewer", "delete", "file", "a.py")
    assert err.value.status_code == 403
    table = acl.matrix()
    assert set(table) == set(acl.ROLES)
    assert all(set(v) == set(acl.ACTIONS) for v in table.values())
    assert table["agent"]["publish"] == "none" and table["reviewer"]["approve"] == "all"


def test_media_path_prefix_cannot_be_spoofed():
    assert not acl.is_media_path("src/media/x.py")
    assert not acl.is_media_path("mediax/y")
    assert acl.is_media_path("music/song.json")


def test_module_registry():
    available = [m for m in modules.registry() if m["status"] == "available"]
    planned = [m for m in modules.registry() if m["status"] == "planned"]
    assert [m["id"] for m in available] == ["software", "sound", "music", "film", "animation",
                                             "sdk", "social", "multimedia", "media"]
    assert len(planned) == 16 and all(not m["starter_files"] for m in planned)
    for m in available:
        assert m["crew"] and m["quick_tasks"] and m["starter_files"]
        # Media modules keep their files in media folders so media editors can work on them.
        if m["id"] in ("sound", "music", "film", "animation", "social", "multimedia", "media"):
            assert all(acl.is_media_path(path) for path in m["starter_files"])
    assert modules.crew_steps("software") == []
    assert [s["agent"] for s in modules.crew_steps("music")] == ["composer", "arranger", "rights-checker"]
    assert modules.module_or_default("nope")["id"] == "software"
