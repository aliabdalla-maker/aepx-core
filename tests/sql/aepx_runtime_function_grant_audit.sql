-- Read-only privilege audit: run as each actual untrusted runtime role.
-- No role creation, GRANT/REVOKE, migrations, or trusted completion.
DO $audit$
DECLARE
  schema_row record;
  fn record;
  acl record;
  sensitive_functions text[] := ARRAY[
    'aepx_iteration.claim',
    'aepx_iteration.advance',
    'aepx_iteration.renew',
    'aepx_iteration.consume_approval',
    'aepx_budget.reserve',
    'aepx_budget.settle'
  ];
  found_count integer := 0;
BEGIN
  IF (SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user)
     IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'DENY: runtime role bypasses RLS';
  END IF;
  FOR schema_row IN
    SELECT oid,nspname,nspowner,nspacl
    FROM pg_namespace WHERE nspname IN ('aepx_iteration','aepx_budget')
  LOOP
    IF has_schema_privilege(current_user,schema_row.oid,'CREATE') THEN
      RAISE EXCEPTION 'DENY: runtime role can create objects in schema %',schema_row.nspname;
    END IF;
    IF EXISTS (
      SELECT 1 FROM aclexplode(coalesce(schema_row.nspacl,acldefault('n',schema_row.nspowner))) a
      WHERE a.grantee=0 AND a.privilege_type='CREATE'
    ) THEN
      RAISE EXCEPTION 'DENY: PUBLIC has schema CREATE on %',schema_row.nspname;
    END IF;
    found_count:=found_count+1;
    RAISE NOTICE 'PASS: schema % denies runtime and PUBLIC CREATE',schema_row.nspname;
  END LOOP;
  IF found_count<>2 THEN
    RAISE EXCEPTION 'DENY: required schemas missing';
  END IF;
  FOR fn IN
    SELECT p.oid,p.proname,p.proowner,p.proacl,p.prosecdef,n.nspname
    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname IN ('aepx_iteration','aepx_budget')
      AND n.nspname||'.'||p.proname=ANY(sensitive_functions)
  LOOP
    IF EXISTS (
      SELECT 1 FROM aclexplode(coalesce(fn.proacl,acldefault('f',fn.proowner))) a
      WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
    ) THEN
      RAISE EXCEPTION 'DENY: PUBLIC can execute sensitive function %.%',fn.nspname,fn.proname;
    END IF;
    IF pg_has_role(current_user,fn.proowner,'MEMBER') THEN
      RAISE EXCEPTION 'DENY: runtime role belongs to sensitive function owner';
    END IF;
    RAISE NOTICE 'PASS: %.% denies PUBLIC EXECUTE; SECURITY DEFINER=%; runtime EXECUTE=%',
      fn.nspname,fn.proname,fn.prosecdef,
      has_function_privilege(current_user,fn.oid,'EXECUTE');
  END LOOP;
  RAISE NOTICE 'Audit passed limited grant checks; tenant GUC spoofing and reviewer authentication NOT solved';
END
$audit$;
