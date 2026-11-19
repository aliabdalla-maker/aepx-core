# PostgreSQL audit role membership function signatures

The three read-only PostgreSQL security audit scripts now resolve both role arguments to OIDs before calling `pg_has_role(oid, oid, 'MEMBER')`. This avoids relying on a mixed `(name, oid, text)` overload. The caller role OID is selected from `pg_roles` using `current_user` (or the existing local `role_name` variable).

Static tests verify that the old mixed argument patterns are absent. This change does **not** execute PostgreSQL or verify real role grants. Run the existing guarded local audit launchers against a disposable PostgreSQL instance with a non-superuser, non-BYPASSRLS role before treating any security audit as passed. The user-settable `app.tenant_id` GUC is still not a trusted authorization boundary. No migrations, deployments or role grants are performed.
