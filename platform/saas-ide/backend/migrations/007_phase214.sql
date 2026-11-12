-- Phase 2.14: durable MCP dispatch ledger; no automatic replay of uncertain outcomes.
CREATE TABLE IF NOT EXISTS ide_mcp_executions (
 id VARCHAR(36) PRIMARY KEY,
 tenant_id VARCHAR(128) NOT NULL,
 run_id VARCHAR(36) NOT NULL,
 approval_id VARCHAR(36) NOT NULL,
 idempotency_key VARCHAR(160) NOT NULL,
 state VARCHAR(24) NOT NULL DEFAULT 'reserved'
   CHECK(state IN ('reserved','dispatching','succeeded','failed','outcome_unknown')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 dispatch_started_at TIMESTAMPTZ,
 completed_at TIMESTAMPTZ,
 reconciliation_reference VARCHAR(160),
 reconciled_by VARCHAR(255),
 UNIQUE(tenant_id,approval_id),
 UNIQUE(tenant_id,idempotency_key),
 FOREIGN KEY(tenant_id,run_id) REFERENCES ide_agent_runs(tenant_id,id),
 FOREIGN KEY(approval_id) REFERENCES ide_tool_approvals(id)
);
CREATE INDEX IF NOT EXISTS ide_mcp_executions_recovery
 ON ide_mcp_executions(tenant_id,state,dispatch_started_at);
ALTER TABLE ide_mcp_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_mcp_executions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ide_mcp_executions_tenant ON ide_mcp_executions;
CREATE POLICY ide_mcp_executions_tenant ON ide_mcp_executions
 USING (tenant_id=NULLIF(current_setting('ide.tenant_id',true),''))
 WITH CHECK (tenant_id=NULLIF(current_setting('ide.tenant_id',true),''));
