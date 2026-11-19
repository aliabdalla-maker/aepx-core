# PostgreSQL SECURITY DEFINER hardening audit

This read-only, staging-only audit enumerates all existing `SECURITY DEFINER` functions in `aepx_iteration` and `aepx_budget`. It fails if any lacks a fixed `search_path`, permits schemas beyond `pg_catalog, pg_temp`, grants EXECUTE to PUBLIC, or is owned by a role accessible to the current runtime role. Definer functions must fully qualify all application objects.

Run only against a disposable local database as each actual runtime role after applying reviewed migrations:

```bash
bash scripts/test_aepx_pg_security_definer.sh --execute aepx_test_privileges
```

This audit does not migrate, revoke privileges, authenticate tenant identity or enable iteration completion. If no definer functions exist, it reports a completed inspection but **does not certify the future trusted-function design**. PostgreSQL execution has not been performed; CI checks only static contracts. The existing `app.tenant_id` session setting is spoofable and must not be used alone for tenant authentication.

## Coverage reporting

The audit fails if either required AEP-X schema is missing. It counts privileged functions actually inspected. A zero count is reported as **NOT ASSESSED**, not a privileged-function security pass. Nonzero inspection is reported with the number of functions covered, limited to the two named schemas. The script remains read-only and has not been executed against PostgreSQL.
