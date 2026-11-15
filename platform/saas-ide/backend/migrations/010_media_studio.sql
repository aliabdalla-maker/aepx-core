-- Media Studio: governed AI media generation, social publishing and the film pipeline.
-- Every row is tenant-scoped and protected by FORCE ROW LEVEL SECURITY (same pattern as 001).
-- A job or post can only run / publish after a human approval bound to its content digest.

CREATE TABLE IF NOT EXISTS ide_media_jobs (
  id UUID PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  requested_by VARCHAR(255) NOT NULL,
  kind VARCHAR(16) NOT NULL CHECK (kind IN ('image', 'video', 'music', 'voice', 'script')),
  provider VARCHAR(32) NOT NULL,
  prompt TEXT NOT NULL CHECK (length(prompt) BETWEEN 1 AND 4000),
  params JSONB NOT NULL DEFAULT '{}'::jsonb,
  digest CHAR(64) NOT NULL,
  estimate_pence INTEGER NOT NULL DEFAULT 0 CHECK (estimate_pence >= 0),
  state VARCHAR(16) NOT NULL DEFAULT 'proposed'
    CHECK (state IN ('proposed', 'approved', 'rejected', 'running', 'succeeded', 'failed')),
  approved_by VARCHAR(255),
  approved_digest CHAR(64),
  external_id VARCHAR(255),
  result_url TEXT,
  result_text TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ide_media_jobs_project_fk FOREIGN KEY (tenant_id, project_id)
    REFERENCES ide_projects (tenant_id, id) ON DELETE CASCADE,
  -- An approval is only valid for the exact content it was given for.
  CONSTRAINT ide_media_jobs_approval_bound CHECK (
    state NOT IN ('approved', 'running', 'succeeded') OR (approved_by IS NOT NULL AND approved_digest = digest))
);
CREATE INDEX IF NOT EXISTS idx_ide_media_jobs_project ON ide_media_jobs (tenant_id, project_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ide_media_jobs_tenant_id ON ide_media_jobs (tenant_id, id);

-- Generated binaries (images, audio) returned inline by providers. Capped at 20 MB each.
CREATE TABLE IF NOT EXISTS ide_media_assets (
  tenant_id VARCHAR(128) NOT NULL,
  job_id UUID NOT NULL,
  content_type VARCHAR(64) NOT NULL,
  sha256 CHAR(64) NOT NULL,
  data BYTEA NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 20971520),
  PRIMARY KEY (tenant_id, job_id),
  CONSTRAINT ide_media_assets_job_fk FOREIGN KEY (tenant_id, job_id)
    REFERENCES ide_media_jobs (tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ide_social_posts (
  id UUID PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  created_by VARCHAR(255) NOT NULL,
  platform VARCHAR(16) NOT NULL
    CHECK (platform IN ('mock', 'mastodon', 'x', 'linkedin', 'youtube', 'tiktok', 'instagram')),
  body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 5000),
  media_job_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  scheduled_for TIMESTAMPTZ,
  digest CHAR(64) NOT NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'draft'
    CHECK (state IN ('draft', 'approved', 'rejected', 'publishing', 'published', 'exported', 'failed')),
  approved_by VARCHAR(255),
  approved_digest CHAR(64),
  external_id VARCHAR(255),
  external_url TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ide_social_posts_project_fk FOREIGN KEY (tenant_id, project_id)
    REFERENCES ide_projects (tenant_id, id) ON DELETE CASCADE,
  CONSTRAINT ide_social_posts_approval_bound CHECK (
    state NOT IN ('approved', 'publishing', 'published', 'exported')
    OR (approved_by IS NOT NULL AND approved_digest = digest))
);
CREATE INDEX IF NOT EXISTS idx_ide_social_posts_project ON ide_social_posts (tenant_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ide_social_posts_due ON ide_social_posts (tenant_id, scheduled_for) WHERE state = 'approved';

CREATE TABLE IF NOT EXISTS ide_media_audit (
  id UUID PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  object_type VARCHAR(16) NOT NULL CHECK (object_type IN ('media_job', 'social_post')),
  object_id UUID NOT NULL,
  actor VARCHAR(255) NOT NULL,
  action VARCHAR(32) NOT NULL,
  digest CHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ide_media_audit_object ON ide_media_audit (tenant_id, object_id, created_at);

ALTER TABLE ide_media_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_media_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_media_assets FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_social_posts FORCE ROW LEVEL SECURITY;
ALTER TABLE ide_media_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_media_audit FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY ide_media_jobs_tenant ON ide_media_jobs
    USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''))
    WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY ide_media_assets_tenant ON ide_media_assets
    USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''))
    WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY ide_social_posts_tenant ON ide_social_posts
    USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''))
    WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
-- Audit is append-only for the runtime role: insert and read, never update or delete.
DO $$ BEGIN
  CREATE POLICY ide_media_audit_tenant_read ON ide_media_audit FOR SELECT
    USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE POLICY ide_media_audit_tenant_insert ON ide_media_audit FOR INSERT
    WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true), ''));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
