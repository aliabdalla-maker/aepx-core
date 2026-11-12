-- Phase 2.3 fenced leases, tenant budgets and immutable spend events.
ALTER TABLE ide_agent_jobs ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 0;
ALTER TABLE ide_agent_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS ide_agent_budgets (
 tenant_id VARCHAR(128) PRIMARY KEY,
 max_tokens BIGINT NOT NULL CHECK(max_tokens>=0),
 max_cost_microusd BIGINT NOT NULL CHECK(max_cost_microusd>=0),
 reserved_tokens BIGINT NOT NULL DEFAULT 0 CHECK(reserved_tokens>=0),
 spent_tokens BIGINT NOT NULL DEFAULT 0 CHECK(spent_tokens>=0),
 reserved_microusd BIGINT NOT NULL DEFAULT 0 CHECK(reserved_microusd>=0),
 spent_microusd BIGINT NOT NULL DEFAULT 0 CHECK(spent_microusd>=0)
);
CREATE UNIQUE INDEX IF NOT EXISTS ide_agent_jobs_tenant_id ON ide_agent_jobs(tenant_id,id);
CREATE TABLE IF NOT EXISTS ide_agent_spend (
 id VARCHAR(36) PRIMARY KEY,
 tenant_id VARCHAR(128) NOT NULL,
 job_id VARCHAR(36) NOT NULL,
 fencing_token BIGINT NOT NULL,
 reserved_tokens INTEGER NOT NULL CHECK(reserved_tokens>=0),
 reserved_microusd BIGINT NOT NULL CHECK(reserved_microusd>=0),
 actual_tokens INTEGER,
 actual_microusd BIGINT,
 state VARCHAR(16) NOT NULL DEFAULT 'reserved' CHECK(state IN ('reserved','settled','released')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,job_id,fencing_token),
 FOREIGN KEY(tenant_id,job_id) REFERENCES ide_agent_jobs(tenant_id,id) ON DELETE CASCADE
);
ALTER TABLE ide_agent_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_agent_budgets FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_agent_spend ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_agent_spend FORCE ROW LEVEL SECURITY;
CREATE POLICY ide_agent_budgets_tenant ON ide_agent_budgets
 USING(tenant_id=NULLIF(current_setting('ide.tenant_id',true),''))
 WITH CHECK(tenant_id=NULLIF(current_setting('ide.tenant_id',true),''));
CREATE POLICY ide_agent_spend_tenant ON ide_agent_spend
 USING(tenant_id=NULLIF(current_setting('ide.tenant_id',true),''))
 WITH CHECK(tenant_id=NULLIF(current_setting('ide.tenant_id',true),''));
