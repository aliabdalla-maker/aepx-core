-- AEP-X transactional engineering iteration state foundation.
-- STAGING / DISPOSABLE DATABASE ONLY. No model execution, provisioning or dispatch.
CREATE SCHEMA IF NOT EXISTS aepx_iteration;

CREATE TABLE IF NOT EXISTS aepx_iteration.work_item (
 tenant_id uuid NOT NULL,
 iteration_number integer NOT NULL CHECK (iteration_number BETWEEN 1 AND 10000),
 stage text NOT NULL DEFAULT 'pending'
   CHECK (stage IN ('pending','requirements','design','patch_proposed','tests_recorded','reviewed','completed')),
 evidence jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence)='object'),
 fence bigint NOT NULL DEFAULT 0 CHECK (fence>=0),
 lease_owner text,
 lease_expires_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (tenant_id,iteration_number),
 CHECK ((lease_owner IS NULL AND lease_expires_at IS NULL) OR
        (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS aepx_iteration_one_incomplete
 ON aepx_iteration.work_item(tenant_id) WHERE stage <> 'completed';

ALTER TABLE aepx_iteration.work_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE aepx_iteration.work_item FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS work_item_tenant_scope ON aepx_iteration.work_item;
CREATE POLICY work_item_tenant_scope ON aepx_iteration.work_item
 USING (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id',true),'')::uuid);

-- An existing row must be provisioned by a trusted controller. No implicit insert.
-- Claiming a live lease is refused, including for the current owner.
CREATE OR REPLACE FUNCTION aepx_iteration.claim(
 p_tenant uuid,p_number integer,p_owner text,p_seconds integer
) RETURNS bigint LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE w aepx_iteration.work_item%ROWTYPE;
BEGIN
 IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
    OR p_number IS NULL OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_-]{1,128}$'
    OR p_seconds IS NULL OR p_seconds NOT BETWEEN 1 AND 600 THEN
   RAISE EXCEPTION 'iteration claim denied';
 END IF;
 SELECT * INTO w FROM aepx_iteration.work_item
 WHERE tenant_id=p_tenant AND iteration_number=p_number FOR UPDATE;
 IF NOT FOUND OR w.stage='completed' THEN RAISE EXCEPTION 'iteration unavailable'; END IF;
 IF w.lease_expires_at IS NOT NULL AND w.lease_expires_at>clock_timestamp() THEN
   RAISE EXCEPTION 'iteration lease active';
 END IF;
 IF w.fence=9223372036854775807 THEN RAISE EXCEPTION 'fence exhausted'; END IF;
 UPDATE aepx_iteration.work_item
 SET fence=fence+1,lease_owner=p_owner,
     lease_expires_at=clock_timestamp()+make_interval(secs=>p_seconds),
     updated_at=clock_timestamp()
 WHERE tenant_id=p_tenant AND iteration_number=p_number
 RETURNING fence INTO w.fence;
 RETURN w.fence;
END $$;

-- The caller must hold the current unexpired lease. Stage evidence is a
-- reference only: signature/provenance and tests are NOT verified here.
CREATE OR REPLACE FUNCTION aepx_iteration.advance(
 p_tenant uuid,p_number integer,p_owner text,p_fence bigint,
 p_stage text,p_evidence text
) RETURNS text LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE w aepx_iteration.work_item%ROWTYPE;
        expected text;
BEGIN
 IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM NULLIF(current_setting('app.tenant_id',true),'')::uuid
    OR p_number IS NULL OR p_owner IS NULL OR p_fence IS NULL OR p_fence<=0
    OR p_stage IS NULL OR p_evidence IS NULL OR length(p_evidence) NOT BETWEEN 1 AND 256 THEN
   RAISE EXCEPTION 'iteration transition denied';
 END IF;
 SELECT * INTO w FROM aepx_iteration.work_item
 WHERE tenant_id=p_tenant AND iteration_number=p_number FOR UPDATE;
 IF NOT FOUND OR w.lease_owner IS DISTINCT FROM p_owner
    OR w.fence IS DISTINCT FROM p_fence OR w.lease_expires_at IS NULL
    OR w.lease_expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'stale or absent iteration lease';
 END IF;
 expected:=CASE w.stage
   WHEN 'pending' THEN 'requirements'
   WHEN 'requirements' THEN 'design'
   WHEN 'design' THEN 'patch_proposed'
   WHEN 'patch_proposed' THEN 'tests_recorded'
   WHEN 'tests_recorded' THEN 'reviewed'
   WHEN 'reviewed' THEN 'completed'
   ELSE NULL END;
 IF p_stage IS DISTINCT FROM expected THEN
   RAISE EXCEPTION 'out-of-order iteration transition';
 END IF;
 UPDATE aepx_iteration.work_item
 SET stage=p_stage,evidence=evidence||jsonb_build_object(p_stage,p_evidence),
     lease_owner=CASE WHEN p_stage='completed' THEN NULL ELSE lease_owner END,
     lease_expires_at=CASE WHEN p_stage='completed' THEN NULL ELSE lease_expires_at END,
     updated_at=clock_timestamp()
 WHERE tenant_id=p_tenant AND iteration_number=p_number;
 RETURN p_stage;
END $$;

REVOKE ALL ON FUNCTION aepx_iteration.claim(uuid,integer,text,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION aepx_iteration.advance(uuid,integer,text,bigint,text,text) FROM PUBLIC;
