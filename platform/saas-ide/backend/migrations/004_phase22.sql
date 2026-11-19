-- Phase 2.2: durable queue, leases and exact-argument tool approval.
ALTER TABLE ide_agent_runs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);
CREATE UNIQUE INDEX IF NOT EXISTS ide_runs_idempotency ON ide_agent_runs(tenant_id,subject,idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS ide_agent_jobs (
 id VARCHAR(36) PRIMARY KEY,
 tenant_id VARCHAR(128) NOT NULL,
 run_id VARCHAR(36) NOT NULL,
 state VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','leased','completed','failed','cancelled')),
 attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt>=0),
 lease_owner VARCHAR(100),
 lease_until TIMESTAMPTZ,
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,run_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES ide_agent_runs(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ide_agent_jobs_ready ON ide_agent_jobs(state,next_attempt_at,lease_until);
CREATE TABLE IF NOT EXISTS ide_tool_approvals (
 id VARCHAR(36) PRIMARY KEY,
 tenant_id VARCHAR(128) NOT NULL,
 run_id VARCHAR(36) NOT NULL,
 server_name VARCHAR(100) NOT NULL,
 tool_name VARCHAR(120) NOT NULL,
 args_sha256 CHAR(64) NOT NULL,
 state VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected','consumed')),
 requested_by VARCHAR(255) NOT NULL,
 decided_by VARCHAR(255),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,run_id,server_name,tool_name,args_sha256),
 FOREIGN KEY(tenant_id,run_id) REFERENCES ide_agent_runs(tenant_id,id) ON DELETE CASCADE
);
DO $$ BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE policyname='ide_agent_jobs_tenant') THEN
    ALTER TABLE ide_agent_jobs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE ide_agent_jobs FORCE ROW LEVEL SECURITY;
    CREATE POLICY ide_agent_jobs_tenant ON ide_agent_jobs
      USING (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''))
      WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''));
  END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE policyname='ide_tool_approvals_tenant') THEN
    ALTER TABLE ide_tool_approvals ENABLE ROW LEVEL SECURITY;
    ALTER TABLE ide_tool_approvals FORCE ROW LEVEL SECURITY;
    CREATE POLICY ide_tool_approvals_tenant ON ide_tool_approvals
      USING (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''))
      WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''));
  END IF;
END $$;
