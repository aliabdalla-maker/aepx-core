-- Phase 2.1: apply with a privileged migration role after 001 and 002.
-- pgvector extension must be installed on the PostgreSQL server image.
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE ide_agent_runs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ide_agent_runs DROP CONSTRAINT IF EXISTS ide_agent_runs_status_check;
ALTER TABLE ide_agent_runs ADD CONSTRAINT ide_agent_runs_status_check CHECK (
  status IN ('awaiting_approval','approved','rejected','running','completed','failed','cancelled'));
CREATE TABLE IF NOT EXISTS ide_agent_audit (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  run_id VARCHAR(36) NOT NULL,
  actor VARCHAR(255) NOT NULL,
  action VARCHAR(50) NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (tenant_id, run_id) REFERENCES ide_agent_runs(tenant_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ide_runs_tenant_id_unique ON ide_agent_runs(tenant_id, id);
-- Ensure the FK is valid for tenant-specific run references.
ALTER TABLE ide_agent_audit DROP CONSTRAINT IF EXISTS ide_agent_audit_tenant_id_run_id_fkey;
ALTER TABLE ide_agent_audit ADD CONSTRAINT ide_agent_audit_run_fk
  FOREIGN KEY (tenant_id,run_id) REFERENCES ide_agent_runs(tenant_id,id) ON DELETE CASCADE;
CREATE TABLE IF NOT EXISTS ide_knowledge_vectors (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  document_id VARCHAR(36) NOT NULL REFERENCES ide_knowledge_documents(id) ON DELETE CASCADE,
  chunk TEXT NOT NULL,
  embedding vector(1536) NOT NULL,
  FOREIGN KEY (tenant_id,project_id) REFERENCES ide_projects(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ide_knowledge_vectors_tenant_project ON ide_knowledge_vectors(tenant_id,project_id);
ALTER TABLE ide_agent_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_agent_audit FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_knowledge_vectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_knowledge_vectors FORCE ROW LEVEL SECURITY;
CREATE POLICY ide_agent_audit_tenant ON ide_agent_audit
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''));
CREATE POLICY ide_knowledge_vectors_tenant ON ide_knowledge_vectors
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id',true),''));
