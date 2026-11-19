# HITL identity database least privilege

The migration defines two **NOLOGIN** roles:
- `aepx_hitl_identity_reader`: SELECT only on the three authoritative
  identity tables. Assign only to the HITL identity-check connection.
- `aepx_hitl_identity_publisher`: read/write the membership and
  revocation snapshots and authority heartbeat, but no TRUNCATE or DDL.
  Assign only to the trusted IdP synchronization service.

Run manually on isolated staging after the existing identity schema and
revision migration. **No database changes have been executed by this PR.**

These are privilege grants, NOT complete tenant isolation. The database
owner, superuser, role inheritance and pre-existing direct grants can
override intended restrictions. Audit `pg_roles`, `pg_auth_members`,
`information_schema.role_table_grants` and ownership before use. Add
RLS/tenant scoping and live privilege-denial integration tests. Do not
grant these roles to a shared application principal. Ensure the trusted
synchronizer emits complete monotonic snapshots before activating routes.

The CI contract test checks migration text only; it does not execute SQL.
No deployment, merge, OCI provisioning or external effects are enabled.
