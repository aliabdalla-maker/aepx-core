-- Review and apply to isolated staging only.
-- A unique event receipt prevents concurrent attempts from acquiring the
-- same remote action. 'uncertain' requires reconciliation, never blind retry.
BEGIN;
CREATE TABLE IF NOT EXISTS hitl.remote_delivery_receipts (
 tenant_id uuid NOT NULL,
 event_id uuid NOT NULL,
 provider text NOT NULL,
 idempotency_key text NOT NULL,
 state text NOT NULL DEFAULT 'reserved'
   CHECK (state IN ('reserved','uncertain','confirmed','failed_safe')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,event_id),
 UNIQUE(tenant_id,provider,idempotency_key),
 FOREIGN KEY(tenant_id,event_id) REFERENCES hitl.outbox(tenant_id,id),
 CHECK(length(btrim(provider)) BETWEEN 1 AND 128),
 CHECK(length(btrim(idempotency_key)) BETWEEN 8 AND 200)
);
ALTER TABLE hitl.remote_delivery_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl.remote_delivery_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS remote_receipts_tenant ON hitl.remote_delivery_receipts;
CREATE POLICY remote_receipts_tenant ON hitl.remote_delivery_receipts
 USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
COMMIT;
