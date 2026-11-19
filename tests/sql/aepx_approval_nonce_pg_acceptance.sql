-- Explicit opt-in disposable local PostgreSQL acceptance; migration pre-applied.
-- Fixture changes are transactionally rolled back.
DO $preflight$
DECLARE bypass boolean; enabled boolean; forced boolean;
BEGIN
 SELECT rolsuper OR rolbypassrls INTO bypass FROM pg_roles WHERE rolname=current_user;
 IF bypass IS DISTINCT FROM false THEN RAISE EXCEPTION 'non-BYPASSRLS non-superuser required'; END IF;
 SELECT relrowsecurity,relforcerowsecurity INTO enabled,forced
 FROM pg_class WHERE oid='aepx_iteration.approval_nonce'::regclass;
 IF enabled IS DISTINCT FROM true OR forced IS DISTINCT FROM true THEN
   RAISE EXCEPTION 'approval FORCE RLS required';
 END IF;
 SELECT relrowsecurity,relforcerowsecurity INTO enabled,forced
 FROM pg_class WHERE oid='aepx_iteration.work_item'::regclass;
 IF enabled IS DISTINCT FROM true OR forced IS DISTINCT FROM true THEN
   RAISE EXCEPTION 'iteration FORCE RLS required';
 END IF;
END
$preflight$;
BEGIN;
SET LOCAL app.tenant_id='11111111-1111-4111-8111-111111111111';
INSERT INTO aepx_iteration.work_item(tenant_id,iteration_number,stage,fence,lease_owner,lease_expires_at)
VALUES ('11111111-1111-4111-8111-111111111111',1,'reviewed',7,'worker-one',clock_timestamp()+interval '60 seconds');
INSERT INTO aepx_iteration.approval_nonce(tenant_id,iteration_number,nonce,lease_fence,reviewer_id,expires_at)
VALUES
('11111111-1111-4111-8111-111111111111',1,'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',7,'reviewer-one',clock_timestamp()+interval '60 seconds'),
('11111111-1111-4111-8111-111111111111',1,'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',7,'reviewer-one',clock_timestamp()-interval '1 second'),
('11111111-1111-4111-8111-111111111111',1,'cccccccc-cccc-4ccc-8ccc-cccccccccccc',6,'reviewer-one',clock_timestamp()+interval '60 seconds'),
('11111111-1111-4111-8111-111111111111',1,'dddddddd-dddd-4ddd-8ddd-dddddddddddd',7,'reviewer-one',clock_timestamp()+interval '60 seconds');
DO $tests$
DECLARE t uuid:='11111111-1111-4111-8111-111111111111';
        nonce_a uuid:='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
        nonce_b uuid:='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
        nonce_c uuid:='cccccccc-cccc-4ccc-8ccc-cccccccccccc';
        nonce_d uuid:='dddddddd-dddd-4ddd-8ddd-dddddddddddd';
        n integer;
BEGIN
 IF aepx_iteration.consume_approval(t,1,nonce_a,7,'reviewer-one') IS DISTINCT FROM true THEN
   RAISE EXCEPTION 'first approval consumption failed';
 END IF;
 BEGIN
   PERFORM aepx_iteration.consume_approval(t,1,nonce_a,7,'reviewer-one');
   RAISE EXCEPTION 'approval replay accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'approval missing expired mismatched or consumed' THEN RAISE; END IF;
 END;
 BEGIN
   PERFORM aepx_iteration.consume_approval(t,1,nonce_b,7,'reviewer-one');
   RAISE EXCEPTION 'expired approval accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'approval missing expired mismatched or consumed' THEN RAISE; END IF;
 END;
 BEGIN
   PERFORM aepx_iteration.consume_approval(t,1,nonce_c,7,'reviewer-one');
   RAISE EXCEPTION 'stale approval fence accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'approval missing expired mismatched or consumed' THEN RAISE; END IF;
 END;
 BEGIN
   PERFORM aepx_iteration.consume_approval(t,1,nonce_d,7,'reviewer-two');
   RAISE EXCEPTION 'wrong reviewer accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'approval missing expired mismatched or consumed' THEN RAISE; END IF;
 END;
 SELECT count(*) INTO n FROM aepx_iteration.approval_nonce
 WHERE tenant_id=t AND consumed_at IS NOT NULL;
 IF n<>1 THEN RAISE EXCEPTION 'incorrect consumption count'; END IF;
 UPDATE aepx_iteration.work_item
 SET lease_expires_at=clock_timestamp()-interval '1 second'
 WHERE tenant_id=t AND iteration_number=1;
 BEGIN
   PERFORM aepx_iteration.consume_approval(t,1,nonce_d,7,'reviewer-one');
   RAISE EXCEPTION 'expired work lease accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'approval has no current reviewed lease' THEN RAISE; END IF;
 END;
END
$tests$;
SET LOCAL app.tenant_id='22222222-2222-4222-8222-222222222222';
DO $tenant$
DECLARE n integer;
BEGIN
 SELECT count(*) INTO n FROM aepx_iteration.approval_nonce
 WHERE tenant_id='11111111-1111-4111-8111-111111111111';
 IF n<>0 THEN RAISE EXCEPTION 'cross-tenant nonce visible'; END IF;
 BEGIN
   PERFORM aepx_iteration.consume_approval('11111111-1111-4111-8111-111111111111',1,
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',7,'reviewer-one');
   RAISE EXCEPTION 'cross-tenant consumption accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'approval consumption denied' THEN RAISE; END IF;
 END;
END
$tenant$;
ROLLBACK;
