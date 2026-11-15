-- CI-ONLY role fixture for a DISPOSABLE localhost database (aepx_test_*).
-- Applied by a superuser AFTER the aepx_iteration / aepx_budget schema files.
-- Two roles, neither superuser nor BYPASSRLS:
--   aepx_ci_controller  trusted controller: may call iteration/approval/budget functions
--   aepx_ci_runtime     untrusted worker: schema USAGE + row access under FORCE RLS only;
--                       never EXECUTE on sensitive functions, never CREATE, never owner.
DO $roles$
BEGIN
  IF current_database() !~ '^aepx_test_[a-z0-9_]{1,40}$' THEN
    RAISE EXCEPTION 'refusing to create CI roles outside a disposable aepx_test_* database';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aepx_ci_controller') THEN
    CREATE ROLE aepx_ci_controller LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aepx_ci_runtime') THEN
    CREATE ROLE aepx_ci_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END
$roles$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA aepx_iteration, aepx_budget FROM PUBLIC;

GRANT USAGE ON SCHEMA aepx_iteration, aepx_budget TO aepx_ci_controller, aepx_ci_runtime;

-- Controller: row access (still filtered by FORCE RLS) and the authorization functions.
GRANT SELECT, INSERT, UPDATE ON aepx_iteration.work_item, aepx_iteration.approval_nonce,
      aepx_budget.tenant_budget, aepx_budget.reservation TO aepx_ci_controller;
-- DELETE only so the concurrency acceptance can remove its own fixture rows.
GRANT DELETE ON aepx_iteration.work_item, aepx_iteration.approval_nonce TO aepx_ci_controller;
GRANT EXECUTE ON FUNCTION
  aepx_iteration.claim(uuid,integer,text,integer),
  aepx_iteration.advance(uuid,integer,text,bigint,text,text),
  aepx_iteration.renew(uuid,integer,text,bigint,integer),
  aepx_iteration.consume_approval(uuid,integer,uuid,bigint,text),
  aepx_budget.reserve(uuid,text,bigint,numeric),
  aepx_budget.settle(uuid,text,bigint,numeric)
  TO aepx_ci_controller;

-- Runtime: read-only rows under FORCE RLS; no function execution.
GRANT SELECT ON aepx_iteration.work_item, aepx_budget.tenant_budget TO aepx_ci_runtime;
