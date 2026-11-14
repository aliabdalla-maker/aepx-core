-- Staging-only read-only audit of SECURITY DEFINER functions in AEP-X schemas.
-- A fixed safe search_path is mandatory; never silently trust caller schemas.
DO $audit$
DECLARE f record; configured_path text; schemas text[]; part text;
BEGIN
 IF (SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user)
    IS DISTINCT FROM false THEN
   RAISE EXCEPTION 'DENY: audit role bypasses RLS';
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
   IF pg_has_role(current_user,f.proowner,'MEMBER') THEN
     RAISE EXCEPTION 'DENY: runtime role is member of SECURITY DEFINER owner';
   END IF;
   RAISE NOTICE 'PASS: SECURITY DEFINER %.% has fixed path and no PUBLIC EXECUTE',
      f.nspname,f.proname;
 END LOOP;
 RAISE NOTICE 'Definer audit complete; no SECURITY DEFINER functions may exist yet';
END
$audit$;
