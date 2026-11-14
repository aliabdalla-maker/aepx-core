# PostgreSQL budget acceptance: RLS preflight

The rollback-only acceptance fixture `tests/sql/aepx_budget_pg_acceptance.sql` now checks the active PostgreSQL role **before** opening its fixture transaction. It refuses superusers and roles with `BYPASSRLS`, and requires both `aepx_budget.tenant_budget` and `aepx_budget.reservation` to have RLS enabled and forced.

Run only against a **disposable local** database after reviewing and separately applying the migration, using a least-privilege non-BYPASSRLS test role with appropriate schema/table/function privileges. The launcher `scripts/test_aepx_pg_budget_acceptance.sh --execute aepx_test_<name>` intentionally refuses nonlocal hosts and non-test names. It does not provision the database or apply migrations.

These tests still do not prove that `app.tenant_id` is authenticated: an arbitrary SQL client able to set that custom GUC could spoof another tenant. Do not expose tenant SQL execution or enable production multi-tenant budget admission until identity is bound to trusted session authority. CI static checks are not a substitute for running the actual PostgreSQL acceptance script under the intended restricted role.
