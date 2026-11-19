-- Apply once as the migration role, before starting the API.
CREATE TABLE IF NOT EXISTS ide_memberships (
  tenant_id VARCHAR(128) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL CHECK (role IN ('owner','admin','editor','viewer')),
  PRIMARY KEY (tenant_id, subject)
);
CREATE TABLE IF NOT EXISTS ide_projects (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  name VARCHAR(120) NOT NULL,
  description TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ide_projects_tenant ON ide_projects (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ide_projects_tenant_id ON ide_projects (tenant_id, id);
CREATE TABLE IF NOT EXISTS ide_workspace_files (
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  path VARCHAR(255) NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (tenant_id, project_id, path),
  CONSTRAINT ide_workspace_project_tenant_fk FOREIGN KEY (tenant_id, project_id)
    REFERENCES ide_projects (tenant_id, id) ON DELETE CASCADE
);
-- Database-level defense in depth. Runtime role must not own tables or have BYPASSRLS.
ALTER TABLE ide_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_projects FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_workspace_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_workspace_files FORCE ROW LEVEL SECURITY;
CREATE POLICY ide_membership_tenant ON ide_memberships
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
CREATE POLICY ide_project_tenant ON ide_projects
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
CREATE POLICY ide_file_tenant ON ide_workspace_files
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
-- Runtime transaction must set SET LOCAL ide.tenant_id after verified token.
-- Bootstrap membership via privileged, audited administrative migration path only.
