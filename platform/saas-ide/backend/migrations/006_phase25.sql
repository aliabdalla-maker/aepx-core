-- Phase 2.5: tenant-scoped recovery state and immutable reconciliation evidence.
ALTER TABLE ide_agent_spend ADD COLUMN IF NOT EXISTS reconciled_at TIMESTAMPTZ;
ALTER TABLE ide_agent_spend ADD COLUMN IF NOT EXISTS reconciliation_reference VARCHAR(160);
CREATE TABLE IF NOT EXISTS ide_agent_reconciliation (
 id VARCHAR(36) PRIMARY KEY,
 tenant_id VARCHAR(128) NOT NULL,
 reservation_id VARCHAR(36) NOT NULL,
 provider_reference VARCHAR(160) NOT NULL,
 actual_tokens BIGINT NOT NULL CHECK(actual_tokens>=0),
 actual_microusd BIGINT NOT NULL CHECK(actual_microusd>=0),
 actor VARCHAR(255) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,provider_reference),
 UNIQUE(tenant_id,reservation_id),
 FOREIGN KEY(reservation_id) REFERENCES ide_agent_spend(id)
);
ALTER TABLE ide_agent_reconciliation ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_agent_reconciliation FORCE ROW LEVEL SECURITY;
CREATE POLICY ide_agent_reconciliation_tenant ON ide_agent_reconciliation
 USING (tenant_id=NULLIF(current_setting('ide.tenant_id',true),''))
 WITH CHECK (tenant_id=NULLIF(current_setting('ide.tenant_id',true),''));
