"""Role-based permissions (FN-02, BE-08, USR-01..05, SET-04). Least privilege: a permission
not listed for a role is denied."""
from __future__ import annotations

ROLES = ("tenant_admin", "it_admin", "security_analyst", "endpoint_user", "auditor", "msp_operator")

_READ = {"devices.read", "alerts.read", "incidents.read", "policies.read", "quarantine.read", "audit.read",
         "assets.read", "integrations.read", "settings.read", "kpi.read", "files.read", "recovery.read",
         "actions.read", "coverage.read"}

PERMISSIONS: dict[str, set[str]] = {
    "auditor": set(_READ),
    "endpoint_user": {"self.devices.read", "self.alerts.read", "quarantine.request_review", "report.suspicious",
                      "notifications.read", "files.read", "files.write", "settings.read"},
    "it_admin": _READ - {"audit.read"} | {
        "devices.enrol", "devices.write", "policies.write", "scans.schedule", "scans.run", "exclusions.write",
        "quarantine.restore", "settings.write", "files.write", "integrations.write", "assets.write",
        "notifications.read", "updates.publish"},
    "security_analyst": _READ - {"audit.read"} | {
        "alerts.write", "incidents.write", "investigations.run", "actions.propose", "actions.approve",
        "recovery.write", "notifications.read", "files.write", "report.suspicious", "traffic.propose"},
    "msp_operator": set(),  # filled below
    "tenant_admin": set(),  # filled below
}
PERMISSIONS["msp_operator"] = PERMISSIONS["it_admin"] | PERMISSIONS["security_analyst"]
PERMISSIONS["tenant_admin"] = (PERMISSIONS["msp_operator"] | {
    "audit.read", "users.manage", "billing.manage", "recovery.approve_return", "traffic.approve",
    "settings.write_sensitive"})


def allowed(roles: set[str], permission: str) -> bool:
    return any(permission in PERMISSIONS.get(r, set()) for r in roles)
