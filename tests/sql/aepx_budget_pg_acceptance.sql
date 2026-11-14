-- Run only on an isolated disposable PostgreSQL database after migration review.
-- All fixture changes roll back. The migration itself is NOT applied by this file.
BEGIN;
SET LOCAL app.tenant_id = '11111111-1111-4111-8111-111111111111';
INSERT INTO aepx_budget.tenant_budget(tenant_id,token_cap,cost_cap)
VALUES ('11111111-1111-4111-8111-111111111111',100,'10.000000');

DO $$
DECLARE tenant uuid := '11111111-1111-4111-8111-111111111111';
        result text;
        tokens bigint;
        cost numeric;
BEGIN
 result := aepx_budget.reserve(tenant,'acceptance-1',40, '4.000000');
 IF result <> 'reserved' THEN RAISE EXCEPTION 'first reservation failed: %',result; END IF;
 result := aepx_budget.reserve(tenant,'acceptance-1',40, '4.000000');
 IF result <> 'already_reserved' THEN RAISE EXCEPTION 'idempotent reservation failed'; END IF;
 BEGIN
   PERFORM aepx_budget.reserve(tenant,'acceptance-1',41,'4.000000');
   RAISE EXCEPTION 'conflicting reservation unexpectedly accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM = 'conflicting reservation unexpectedly accepted' THEN RAISE; END IF;
   IF SQLERRM <> 'conflicting request id' THEN RAISE; END IF;
 END;
 BEGIN
   PERFORM aepx_budget.reserve(tenant,'acceptance-over',61,'7.000000');
   RAISE EXCEPTION 'over-budget reservation unexpectedly accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM = 'over-budget reservation unexpectedly accepted' THEN RAISE; END IF;
   IF SQLERRM <> 'budget exhausted' THEN RAISE; END IF;
 END;
 result := aepx_budget.settle(tenant,'acceptance-1',25,'2.500000');
 IF result <> 'settled' THEN RAISE EXCEPTION 'settlement failed'; END IF;
 result := aepx_budget.settle(tenant,'acceptance-1',25,'2.500000');
 IF result <> 'already_settled' THEN RAISE EXCEPTION 'settlement replay failed'; END IF;
 SELECT token_committed,cost_committed INTO tokens,cost
 FROM aepx_budget.tenant_budget WHERE tenant_id=tenant;
 IF tokens <> 25 OR cost <> 2.5 THEN
   RAISE EXCEPTION 'incorrect budget committed after settlement: %, %',tokens,cost;
 END IF;
 BEGIN
   PERFORM aepx_budget.settle(tenant,'acceptance-1',26,'2.500000');
   RAISE EXCEPTION 'conflicting settlement unexpectedly accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM = 'conflicting settlement unexpectedly accepted' THEN RAISE; END IF;
   IF SQLERRM <> 'conflicting settlement' THEN RAISE; END IF;
 END;
END $$;

-- A second tenant is not permitted to see or modify the first tenant's rows.
SET LOCAL app.tenant_id = '22222222-2222-4222-8222-222222222222';
DO $$
DECLARE n integer;
BEGIN
 SELECT count(*) INTO n FROM aepx_budget.tenant_budget
 WHERE tenant_id='11111111-1111-4111-8111-111111111111';
 IF n <> 0 THEN RAISE EXCEPTION 'cross-tenant budget row visible'; END IF;
 SELECT count(*) INTO n FROM aepx_budget.reservation
 WHERE tenant_id='11111111-1111-4111-8111-111111111111';
 IF n <> 0 THEN RAISE EXCEPTION 'cross-tenant reservation visible'; END IF;
 BEGIN
   PERFORM aepx_budget.reserve('11111111-1111-4111-8111-111111111111','cross-tenant',1,1);
   RAISE EXCEPTION 'cross-tenant reservation unexpectedly accepted';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM = 'cross-tenant reservation unexpectedly accepted' THEN RAISE; END IF;
   IF SQLERRM <> 'budget reservation denied' THEN RAISE; END IF;
 END;
END $$;
ROLLBACK;
