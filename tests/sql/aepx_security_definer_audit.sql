-- Staging-only read-only audit of SECURITY DEFINER functions in AEP-X schemas.
-- A fixed safe search_path is mandatory; never silently trust caller schemas.
DO $audit$
DECLARE f record; configured_path text; inspected integer := 0; schema_count integer;
BEGIN
 IF (SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user)
    IS DISTINCT FROM false THEN
   RAISE EXCEPTION 'DENY: audit role bypasses RLS';
 END IF;
 SELECT count(*) INTO schema_count FROM pg_namespace
 WHERE nspname IN ('aepx_iteration','aepx_budget');
 IF schema_count <> 2 THEN
   RAISE EXCEPTION 'DENY: required AEP-X schemas missing';
 END IF;
 FOR f IN
   SELECT p.oid,p.proname,p.prosecdef,p.proconfig,p.proowner,p.proacl,
          n.nspname
   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname IN ('aepx_iteration','aepx_budget') AND p.prosecdef
 LOOP
   SELECT substring(setting FROM 13) INTO configured_path
   FROM unnest(coalesce(f.proconfig,ARRAY[]::text[])) setting
   WHERE setting LIKE 'search_path=%'
   LIMIT 1;
   IF configured_path IS NULL THEN
     RAISE EXCEPTION 'DENY: SECURITY DEFINER %.% lacks fixed search_path',f.nspname,f.proname;
   END IF;
   -- Restrict to pg_catalog and pg_temp only. Definer code must fully qualify
   -- every application relation and function; pg_temp must be last.
   IF configured_path !~ '^pg_catalog(, *pg_temp)?$' THEN
     RAISE EXCEPTION 'DENY: SECURITY DEFINER %.% unsafe search_path: %',
       f.nspname,f.proname,configured_path;
   END IF;
   IF EXISTS (
     SELECT 1 FROM aclexplode(coalesce(f.proacl,acldefault('f',f.proowner))) a
     WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
   ) THEN
     RAISE EXCEPTION 'DENY: PUBLIC EXECUTE on SECURITY DEFINER %.%',f.nspname,f.proname;
   END IF;
   IF pg_has_role((SELECT oid FROM pg_roles WHERE rolname=current_user),f.proowner,'MEMBER') THEN
     RAISE EXCEPTION 'DENY: runtime role is member of SECURITY DEFINER owner';
   END IF;
   inspected := inspected + 1;
   RAISE NOTICE 'PASS: SECURITY DEFINER %.% has fixed path and no PUBLIC EXECUTE',
      f.nspname,f.proname;
 END LOOP;
 IF inspected=0 THEN
   RAISE NOTICE 'NOT ASSESSED: zero SECURITY DEFINER functions found; no privileged-function security claim';
 ELSE
   RAISE NOTICE 'PASS: inspected % SECURITY DEFINER functions; scope limited to AEP-X schemas',inspected;
 END IF;
END
$audit$;
