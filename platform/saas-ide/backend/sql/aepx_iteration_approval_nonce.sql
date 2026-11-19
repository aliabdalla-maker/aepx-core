-- Staging-only approval consumption foundation. Not an authorization to complete.
-- Trusted service must authenticate tenant, reviewer and signature independently.
CREATE SCHEMA IF NOT EXISTS aepx_iteration;
CREATE TABLE IF NOT EXISTS aepx_iteration.approval_nonce (
 tenant_id uuid NOT NULL,
 iteration_number integer NOT NULL CHECK (iteration_number BETWEEN 1 AND 10000),
 nonce uuid NOT NULL,
 lease_fence bigint NOT NULL CHECK (lease_fence>0),
 reviewer_id text NOT NULL CHECK (reviewer_id ~ '^[A-Za-z0-9_-]{1,128}$'),
 expires_at timestamptz NOT NULL,
 consumed_at timestamptz,
 PRIMARY KEY (tenant_id,nonce)
);
ALTER TABLE aepx_iteration.approval_nonce ENABLE ROW LEVEL SECURITY;
ALTER TABLE aepx_iteration.approval_nonce FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS approval_nonce_tenant_scope ON aepx_iteration.approval_nonce;
CREATE POLICY approval_nonce_tenant_scope ON aepx_iteration.approval_nonce
 USING (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id=NULLIF(current_setting('app.tenant_id',true),'')::uuid);

-- The trusted controller must provision a nonce only AFTER authenticating the
-- reviewer and verifying the signed evidence. This function cannot do either.
CREATE OR REPLACE FUNCTION aepx_iteration.consume_approval(
 p_tenant uuid,p_number integer,p_nonce uuid,p_fence bigint,p_reviewer text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE w aepx_iteration.work_item%ROWTYPE;
        a aepx_iteration.approval_nonce%ROWTYPE;
BEGIN
 IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
    OR p_number IS NULL OR p_number NOT BETWEEN 1 AND 10000
    OR p_nonce IS NULL OR p_fence IS NULL OR p_fence<=0
    OR p_reviewer IS NULL OR p_reviewer !~ '^[A-Za-z0-9_-]{1,128}$' THEN
   RAISE EXCEPTION 'approval consumption denied';
 END IF;
 -- Fixed lock order: work item, then approval. Prevent stale-fence consumption.
 SELECT * INTO w FROM aepx_iteration.work_item
 WHERE tenant_id=p_tenant AND iteration_number=p_number FOR UPDATE;
 IF NOT FOUND OR w.stage<>'reviewed' OR w.fence<>p_fence
    OR w.lease_expires_at IS NULL OR w.lease_expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'approval has no current reviewed lease';
 END IF;
 SELECT * INTO a FROM aepx_iteration.approval_nonce
 WHERE tenant_id=p_tenant AND nonce=p_nonce FOR UPDATE;
 IF NOT FOUND OR a.iteration_number<>p_number OR a.lease_fence<>p_fence
    OR a.reviewer_id<>p_reviewer OR a.expires_at<=clock_timestamp()
    OR a.consumed_at IS NOT NULL THEN
   RAISE EXCEPTION 'approval missing expired mismatched or consumed';
 END IF;
 UPDATE aepx_iteration.approval_nonce
 SET consumed_at=clock_timestamp()
 WHERE tenant_id=p_tenant AND nonce=p_nonce;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION aepx_iteration.consume_approval(uuid,integer,uuid,bigint,text) FROM PUBLIC;
-- No terminal completion function or automatic approval creation is provided.
