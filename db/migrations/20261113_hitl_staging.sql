-- AEP-X staging migration draft. Apply only after review and with a migration tool.
-- Application must set app.tenant_id from a VERIFIED authentication context.
BEGIN;
CREATE SCHEMA IF NOT EXISTS hitl;
CREATE TABLE IF NOT EXISTS hitl.approvals (
 id uuid PRIMARY KEY,
 tenant_id uuid NOT NULL,
 action_hash char(64) NOT NULL,
 requester_id text NOT NULL,
 approver_id text,
 status text NOT NULL CHECK (status IN ('pending','approved','rejected','consumed')),
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 consumed_at timestamptz,
 CHECK (requester_id <> approver_id OR approver_id IS NULL)
);
CREATE INDEX IF NOT EXISTS approvals_tenant_status_idx ON hitl.approvals(tenant_id,status,expires_at);
CREATE TABLE IF NOT EXISTS hitl.events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id uuid NOT NULL,
 approval_id uuid NOT NULL REFERENCES hitl.approvals(id),
 event text NOT NULL,
 actor_id text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hitl.outbox (
 id uuid PRIMARY KEY,
 tenant_id uuid NOT NULL,
 idempotency_key text NOT NULL,
 topic text NOT NULL,
 payload jsonb NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivered')),
 attempts integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),
 delivered_at timestamptz,
 UNIQUE(tenant_id,idempotency_key)
);
ALTER TABLE hitl.approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl.outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl.approvals FORCE ROW LEVEL SECURITY;
ALTER TABLE hitl.events FORCE ROW LEVEL SECURITY;
ALTER TABLE hitl.outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS approvals_tenant ON hitl.approvals;
CREATE POLICY approvals_tenant ON hitl.approvals
 USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);
DROP POLICY IF EXISTS events_tenant ON hitl.events;
CREATE POLICY events_tenant ON hitl.events
 USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);
DROP POLICY IF EXISTS outbox_tenant ON hitl.outbox;
CREATE POLICY outbox_tenant ON hitl.outbox
 USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
 WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);
COMMIT;
