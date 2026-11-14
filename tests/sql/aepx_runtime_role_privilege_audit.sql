-- Read-only fail-closed audit of the CURRENT connected application/worker role.
-- Run separately for every runtime role in a disposable local PostgreSQL database.
-- This does not prove identity binding or make a user-settable GUC trustworthy.
DO $audit$
DECLARE
  role_name name := current_user;
  is_privileged boolean;
  target regclass;
  rel_rls boolean;
  rel_force boolean;
  rel_owner oid;
  relation_name text;
BEGIN
  SELECT rolsuper OR rolbypassrls INTO is_privileged
  FROM pg_roles WHERE rolname=role_name;
  IF is_privileged IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'DENY: runtime role is superuser or BYPASSRLS';
  END IF;
  FOREACH relation_name IN ARRAY ARRAY[
    'aepx_iteration.work_item',
    'aepx_iteration.approval_nonce',
    'aepx_budget.tenant_budget',
    'aepx_budget.reservation'
  ] LOOP
    target := to_regclass(relation_name);
    IF target IS NULL THEN
      RAISE EXCEPTION 'DENY: required relation missing: %',relation_name;
    END IF;
    SELECT relrowsecurity,relforcerowsecurity,relowner
      INTO rel_rls,rel_force,rel_owner FROM pg_class WHERE oid=target;
    IF rel_rls IS DISTINCT FROM true OR rel_force IS DISTINCT FROM true THEN
      RAISE EXCEPTION 'DENY: FORCE RLS missing on %',relation_name;
    END IF;
    IF pg_has_role((SELECT oid FROM pg_roles WHERE rolname=role_name),rel_owner,'MEMBER') THEN
      RAISE EXCEPTION 'DENY: runtime role is member of table owner on %',relation_name;
    END IF;
    IF has_table_privilege(role_name,target,'INSERT')
       OR has_table_privilege(role_name,target,'UPDATE')
       OR has_table_privilege(role_name,target,'DELETE')
       OR has_table_privilege(role_name,target,'TRUNCATE')
       OR has_table_privilege(role_name,target,'REFERENCES')
       OR has_table_privilege(role_name,target,'TRIGGER') THEN
      RAISE EXCEPTION 'DENY: runtime role has direct table mutation privilege on %',relation_name;
    END IF;
    RAISE NOTICE 'PASS: % has FORCE RLS and no direct mutation privileges for %',relation_name,role_name;
  END LOOP;
  RAISE NOTICE 'PASS: current role direct-DML audit only; tenant GUC and function privileges remain untrusted';
END
$audit$;
