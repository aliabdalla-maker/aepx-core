-- AEP-X offline PostgreSQL budget foundation. Not wired to provider execution.
-- Apply only in disposable staging after review; application role must not own tables.
CREATE SCHEMA IF NOT EXISTS aepx_budget;

CREATE TABLE IF NOT EXISTS aepx_budget.tenant_budget (
 tenant_id uuid PRIMARY KEY,
 token_cap bigint NOT NULL CHECK (token_cap >= 0),
 cost_cap numeric(20,6) NOT NULL CHECK (cost_cap >= 0),
 token_committed bigint NOT NULL DEFAULT 0 CHECK (token_committed >= 0),
 cost_committed numeric(20,6) NOT NULL DEFAULT 0 CHECK (cost_committed >= 0),
 CHECK (token_committed <= token_cap AND cost_committed <= cost_cap)
);

CREATE TABLE IF NOT EXISTS aepx_budget.reservation (
 tenant_id uuid NOT NULL REFERENCES aepx_budget.tenant_budget(tenant_id),
 request_id text NOT NULL CHECK (length(request_id) BETWEEN 1 AND 128 AND request_id ~ '^[A-Za-z0-9_-]+$'),
 reserved_tokens bigint NOT NULL CHECK (reserved_tokens >= 0),
 reserved_cost numeric(20,6) NOT NULL CHECK (reserved_cost >= 0),
 actual_tokens bigint CHECK (actual_tokens >= 0),
 actual_cost numeric(20,6) CHECK (actual_cost >= 0),
 state text NOT NULL DEFAULT 'reserved' CHECK (state IN ('reserved','settled')),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,request_id),
 CHECK ((state='reserved' AND actual_tokens IS NULL AND actual_cost IS NULL) OR
        (state='settled' AND actual_tokens IS NOT NULL AND actual_cost IS NOT NULL
         AND actual_tokens <= reserved_tokens AND actual_cost <= reserved_cost))
);

ALTER TABLE aepx_budget.tenant_budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE aepx_budget.tenant_budget FORCE ROW LEVEL SECURITY;
ALTER TABLE aepx_budget.reservation ENABLE ROW LEVEL SECURITY;
ALTER TABLE aepx_budget.reservation FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_budget_scope ON aepx_budget.tenant_budget;
CREATE POLICY tenant_budget_scope ON aepx_budget.tenant_budget
 USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid);
DROP POLICY IF EXISTS reservation_scope ON aepx_budget.reservation;
CREATE POLICY reservation_scope ON aepx_budget.reservation
 USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid);

-- Call inside a transaction after SET LOCAL app.tenant_id to an authenticated tenant.
-- IMPORTANT: already_reserved and already_settled are NOT authorization to dispatch.
-- Only a new 'reserved' response may authorize a first dispatch, with a separate
-- durable provider idempotency key and fenced lease.
-- Requires a pre-provisioned tenant_budget row; no implicit tenant creation.
CREATE OR REPLACE FUNCTION aepx_budget.reserve(
 p_tenant uuid, p_request text, p_tokens bigint, p_cost numeric
) RETURNS text LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE b aepx_budget.tenant_budget%ROWTYPE;
        e aepx_budget.reservation%ROWTYPE;
BEGIN
 IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
    OR p_request IS NULL OR p_request !~ '^[A-Za-z0-9_-]{1,128}$'
    OR p_tokens IS NULL OR p_tokens < 0 OR p_cost IS NULL OR p_cost < 0
    OR p_cost > 99999999999999 OR round(p_cost,6) <> p_cost THEN
   RAISE EXCEPTION 'budget reservation denied';
 END IF;
 SELECT * INTO b FROM aepx_budget.tenant_budget WHERE tenant_id=p_tenant FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'tenant budget missing'; END IF;
 SELECT * INTO e FROM aepx_budget.reservation
   WHERE tenant_id=p_tenant AND request_id=p_request;
 IF FOUND THEN
   IF e.reserved_tokens <> p_tokens OR e.reserved_cost <> p_cost THEN
     RAISE EXCEPTION 'conflicting request id';
   END IF;
   IF e.state = 'settled' THEN
     RETURN 'already_settled';
   END IF;
   RETURN 'already_reserved';
 END IF;
 IF b.token_committed > b.token_cap-p_tokens OR b.cost_committed > b.cost_cap-p_cost THEN
   RAISE EXCEPTION 'budget exhausted';
 END IF;
 INSERT INTO aepx_budget.reservation(tenant_id,request_id,reserved_tokens,reserved_cost)
 VALUES(p_tenant,p_request,p_tokens,p_cost);
 UPDATE aepx_budget.tenant_budget
 SET token_committed=token_committed+p_tokens, cost_committed=cost_committed+p_cost
 WHERE tenant_id=p_tenant;
 RETURN 'reserved';
END $$;

CREATE OR REPLACE FUNCTION aepx_budget.settle(
 p_tenant uuid,p_request text,p_actual_tokens bigint,p_actual_cost numeric
) RETURNS text LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE e aepx_budget.reservation%ROWTYPE;
BEGIN
 IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
 OR p_request IS NULL OR p_actual_tokens IS NULL OR p_actual_tokens < 0
 OR p_actual_cost IS NULL OR p_actual_cost < 0 OR round(p_actual_cost,6) <> p_actual_cost THEN
   RAISE EXCEPTION 'budget settlement denied';
 END IF;
 PERFORM 1 FROM aepx_budget.tenant_budget WHERE tenant_id=p_tenant FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'tenant budget missing'; END IF;
 SELECT * INTO e FROM aepx_budget.reservation WHERE tenant_id=p_tenant AND request_id=p_request FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'reservation missing'; END IF;
 IF p_actual_tokens > e.reserved_tokens OR p_actual_cost > e.reserved_cost THEN
   RAISE EXCEPTION 'settlement exceeds reservation';
 END IF;
 IF e.state='settled' THEN
   IF e.actual_tokens <> p_actual_tokens OR e.actual_cost <> p_actual_cost THEN
     RAISE EXCEPTION 'conflicting settlement';
   END IF;
   RETURN 'already_settled';
 END IF;
 UPDATE aepx_budget.reservation SET state='settled',actual_tokens=p_actual_tokens,
 actual_cost=p_actual_cost WHERE tenant_id=p_tenant AND request_id=p_request;
 UPDATE aepx_budget.tenant_budget SET
 token_committed=token_committed-(e.reserved_tokens-p_actual_tokens),
 cost_committed=cost_committed-(e.reserved_cost-p_actual_cost)
 WHERE tenant_id=p_tenant;
 RETURN 'settled';
END $$;

-- SECURITY: REVOKE default PUBLIC function execution; explicitly grant only
-- to a separately provisioned least-privilege application role after review.
REVOKE ALL ON FUNCTION aepx_budget.reserve(uuid,text,bigint,numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION aepx_budget.settle(uuid,text,bigint,numeric) FROM PUBLIC;
