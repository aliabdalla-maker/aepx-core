# PostgreSQL runtime role privilege audit

The staging-only SQL audit checks the connected role is not superuser/BYPASSRLS, is not a member of the owners of iteration work items, approval nonces or budget tables, has no direct INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER privileges, and that all four tables enforce FORCE RLS. It raises an error on any failed check.

Run against each real worker/API role in a disposable local database after migrations:

```bash
bash scripts/test_aepx_pg_runtime_privileges.sh --execute aepx_test_privileges
```

The launcher requires an explicit opt-in, restricts the database name and host, and sets PostgreSQL's default transaction mode read-only. CI performs static contract checks only. **The SQL has not been executed against PostgreSQL.**

**Architectural blocker:** Existing `SECURITY INVOKER` iteration and approval functions require underlying table DML grants, so runtime roles cannot both pass this strict no-direct-DML audit and execute those functions. This audit intentionally exposes that incompatibility rather than pretending privileges are safe. A carefully reviewed `SECURITY DEFINER` service-role architecture, hardened `search_path`, function-level EXECUTE grants, and trusted authenticated tenant binding are required before enabling completion. A user-settable `app.tenant_id` GUC is not an authentication boundary. Never use this audit as evidence that approval signatures, reviewer identities or external provider execution are safe.
