-- Disposable staging first. Receipts are atomic with local DB-side effects.
BEGIN;
CREATE TABLE IF NOT EXISTS hitl.execution_receipts (
 tenant_id uuid NOT NULL,
 event_id uuid NOT NULL,
 action_hash char(64) NOT NULL,
 tool_name text NOT NULL,
 executed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (tenant_id,event_id),
 CONSTRAINT receipt_event_fk FOREIGN KEY (tenant_id,event_id)
 REFERENCES hitl.outbox(tenant_id,id),
 CONSTRAINT receipt_tool_name_nonempty CHECK (length(btrim(tool_name)) BETWEEN 1 AND 128)
);
ALTER TABLE hitl.execution_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl.execution_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS receipts_tenant ON hitl.execution_receipts;
CREATE POLICY receipts_tenant ON hitl.execution_receipts
 USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
COMMIT;
