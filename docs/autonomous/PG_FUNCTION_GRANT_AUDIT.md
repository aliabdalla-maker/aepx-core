# PostgreSQL schema and function grant audit

A second read-only staging audit inspects the connected runtime role for schema CREATE privileges and PUBLIC schema CREATE on `aepx_iteration` and `aepx_budget`. It checks that sensitive iteration and budget functions do not grant EXECUTE to PUBLIC and that the runtime role is not a member of their owner role. It requires all four iteration functions (`claim`, `advance`, `renew`, `consume_approval`) to exist.

After migrations in a disposable local database, connect as each actual runtime role and run:

```bash
bash scripts/test_aepx_pg_function_grants.sh --execute aepx_test_privileges
```

The launcher is explicit opt-in, localhost-only and sets default_transaction_read_only. The GitHub workflow runs only static contract tests. **No PostgreSQL audit has been executed.**

This audit is not a proof of authenticated tenant identity. The `app.tenant_id` GUC remains user-settable. No grants are modified. Existing `SECURITY INVOKER` mutation functions remain incompatible with removing direct DML from runtime roles; trusted service-role design and privilege-separated `SECURITY DEFINER` functions need independent security review, including fixed `search_path`, ownership, execution grants and non-spoofable tenant context. Completion remains blocked.
