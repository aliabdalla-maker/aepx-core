-- Explicit opt-in, disposable local PostgreSQL only. Migration must exist already.
-- All fixture rows are rolled back. Run as non-superuser/non-BYPASSRLS.
DO $preflight$
DECLARE bypass boolean; enabled boolean; forced boolean;
BEGIN
 SELECT rolsuper OR rolbypassrls INTO bypass FROM pg_roles WHERE rolname=current_user;
 IF bypass IS DISTINCT FROM false THEN
   RAISE EXCEPTION 'acceptance requires non-BYPASSRLS non-superuser';
 END IF;
 SELECT relrowsecurity,relforcerowsecurity INTO enabled,forced
 FROM pg_class WHERE oid='aepx_iteration.work_item'::regclass;
 IF enabled IS DISTINCT FROM true OR forced IS DISTINCT FROM true THEN
   RAISE EXCEPTION 'acceptance requires FORCE RLS';
 END IF;
END
$preflight$;
BEGIN;
SET LOCAL app.tenant_id='11111111-1111-4111-8111-111111111111';
INSERT INTO aepx_iteration.work_item(tenant_id,iteration_number)
VALUES ('11111111-1111-4111-8111-111111111111',1);
DO $tests$
DECLARE t uuid:='11111111-1111-4111-8111-111111111111';
        f bigint; renewed timestamptz; result text; n integer;
BEGIN
 f:=aepx_iteration.claim(t,1,'worker-one',60);
 IF f<>1 THEN RAISE EXCEPTION 'initial fence incorrect'; END IF;
 BEGIN
   PERFORM aepx_iteration.claim(t,1,'worker-two',60);
   RAISE EXCEPTION 'live lease takeover accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'iteration lease active' THEN RAISE; END IF;
 END;
 renewed:=aepx_iteration.renew(t,1,'worker-one',f,60);
 IF renewed<=clock_timestamp() THEN RAISE EXCEPTION 'renewal not future'; END IF;
 BEGIN
   PERFORM aepx_iteration.renew(t,1,'worker-two',f,60);
   RAISE EXCEPTION 'wrong owner renewed lease';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'stale or expired iteration lease' THEN RAISE; END IF;
 END;
 BEGIN
   PERFORM aepx_iteration.advance(t,1,'worker-one',f,'design','sha256:bad');
   RAISE EXCEPTION 'out-of-order transition accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'out-of-order iteration transition' THEN RAISE; END IF;
 END;
 result:=aepx_iteration.advance(t,1,'worker-one',f,'requirements','sha256:requirements');
 IF result<>'requirements' THEN RAISE EXCEPTION 'requirements failed'; END IF;
 UPDATE aepx_iteration.work_item
 SET lease_expires_at=clock_timestamp()-interval '1 second'
 WHERE tenant_id=t AND iteration_number=1;
 BEGIN
   PERFORM aepx_iteration.renew(t,1,'worker-one',f,60);
   RAISE EXCEPTION 'expired renewal accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'stale or expired iteration lease' THEN RAISE; END IF;
 END;
 f:=aepx_iteration.claim(t,1,'worker-two',60);
 IF f<>2 THEN RAISE EXCEPTION 'reclaim did not increment fence'; END IF;
 BEGIN
   PERFORM aepx_iteration.advance(t,1,'worker-one',1,'design','sha256:stale');
   RAISE EXCEPTION 'stale fence transition accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'stale or absent iteration lease' THEN RAISE; END IF;
 END;
 result:=aepx_iteration.advance(t,1,'worker-two',f,'design','sha256:design');
 IF result<>'design' THEN RAISE EXCEPTION 'reclaimed worker transition failed'; END IF;
 SELECT count(*) INTO n FROM aepx_iteration.work_item WHERE tenant_id=t AND stage='design';
 IF n<>1 THEN RAISE EXCEPTION 'stage not persisted'; END IF;
END
$tests$;
SET LOCAL app.tenant_id='22222222-2222-4222-8222-222222222222';
DO $tenant$
DECLARE n integer;
BEGIN
 SELECT count(*) INTO n FROM aepx_iteration.work_item
 WHERE tenant_id='11111111-1111-4111-8111-111111111111';
 IF n<>0 THEN RAISE EXCEPTION 'cross-tenant work item visible'; END IF;
 BEGIN
   PERFORM aepx_iteration.claim('11111111-1111-4111-8111-111111111111',1,'attacker',60);
   RAISE EXCEPTION 'cross-tenant claim accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'iteration claim denied' THEN RAISE; END IF;
 END;
END
$tenant$;
ROLLBACK;
