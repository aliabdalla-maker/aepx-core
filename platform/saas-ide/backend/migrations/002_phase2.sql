-- Run as privileged migration role; never as the runtime role.
CREATE TABLE IF NOT EXISTS ide_agent_runs (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  request TEXT NOT NULL,
  model_route VARCHAR(40) NOT NULL,
  status VARCHAR(30) NOT NULL CHECK (status IN ('awaiting_approval','approved','rejected','completed','failed')),
  plan TEXT NOT NULL,
  result TEXT NOT NULL DEFAULT '',
  CONSTRAINT ide_agent_run_project_fk FOREIGN KEY (tenant_id,project_id)
    REFERENCES ide_projects(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ide_agent_runs_tenant ON ide_agent_runs(tenant_id);
CREATE TABLE IF NOT EXISTS ide_knowledge_documents (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  title VARCHAR(160) NOT NULL,
  content TEXT NOT NULL,
  CONSTRAINT ide_knowledge_project_fk FOREIGN KEY (tenant_id,project_id)
    REFERENCES ide_projects(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ide_knowledge_tenant_project ON ide_knowledge_documents(tenant_id,project_id);
ALTER TABLE ide_agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_agent_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_knowledge_documents FORCE ROW LEVEL SECURITY;
CREATE POLICY ide_agent_runs_tenant ON ide_agent_runs
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''));
CREATE POLICY ide_knowledge_tenant ON ide_knowledge_documents
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''));
-- Runtime role: GRANT SELECT,INSERT,UPDATE ON ide_agent_runs;
-- Runtime role: GRANT SELECT,INSERT ON ide_knowledge_documents;
