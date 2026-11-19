-- Universal IDE platform (spec §5 ACL, §6 CRUD, §2-4 modules). Apply as the migration role.

-- §5 roles: reviewer (read + approve) and media_editor (media assets only).
DO $$
DECLARE c TEXT;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint
           WHERE conrelid = 'ide_memberships'::regclass AND contype = 'c'
             AND pg_get_constraintdef(oid) LIKE '%role%' LOOP
    EXECUTE format('ALTER TABLE ide_memberships DROP CONSTRAINT %I', c);
  END LOOP;
END $$;
ALTER TABLE ide_memberships ADD CONSTRAINT ide_memberships_role_check
  CHECK (role IN ('owner','admin','editor','media_editor','reviewer','viewer'));

-- §2-4 modules and §6 safe (recoverable) project deletion.
ALTER TABLE ide_projects ADD COLUMN IF NOT EXISTS module VARCHAR(32) NOT NULL DEFAULT 'software';
ALTER TABLE ide_projects ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- §6 versioning and restore: every save, delete and restore of a file is a numbered version.
CREATE TABLE IF NOT EXISTS ide_file_versions (
  tenant_id VARCHAR(128) NOT NULL,
  project_id VARCHAR(36) NOT NULL,
  path VARCHAR(255) NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 1),
  op VARCHAR(16) NOT NULL CHECK (op IN ('save','delete','restore')),
  content TEXT NOT NULL,
  author VARCHAR(255) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, project_id, path, version),
  FOREIGN KEY (tenant_id, project_id) REFERENCES ide_projects(tenant_id, id) ON DELETE CASCADE
);
ALTER TABLE ide_file_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_file_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ide_file_versions_tenant ON ide_file_versions;
CREATE POLICY ide_file_versions_tenant ON ide_file_versions
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''));

-- §5 tamper-evident audit trail: append-only via one function; each event hashes the previous.
CREATE TABLE IF NOT EXISTS ide_audit_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  actor VARCHAR(255) NOT NULL,
  action VARCHAR(64) NOT NULL,
  resource_type VARCHAR(32) NOT NULL,
  resource_id VARCHAR(400) NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  prev_hash CHAR(64) NOT NULL,
  hash CHAR(64) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ide_audit_events_tenant ON ide_audit_events(tenant_id, id);
ALTER TABLE ide_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_audit_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ide_audit_events_tenant ON ide_audit_events;
CREATE POLICY ide_audit_events_tenant ON ide_audit_events
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''));

CREATE OR REPLACE FUNCTION ide_append_audit(p_tenant VARCHAR, p_actor VARCHAR, p_action VARCHAR,
                                            p_type VARCHAR, p_resource VARCHAR, p_detail TEXT)
RETURNS CHAR(64)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE prev CHAR(64); h CHAR(64); ts TIMESTAMPTZ := date_trunc('milliseconds', clock_timestamp());
BEGIN
  -- Only the caller's own tenant scope may be written.
  IF p_tenant IS DISTINCT FROM NULLIF(current_setting('ide.tenant_id', true), '') THEN
    RAISE EXCEPTION 'audit tenant mismatch' USING ERRCODE = '42501';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('ide_audit:' || p_tenant));
  SELECT e.hash INTO prev FROM ide_audit_events e WHERE e.tenant_id = p_tenant ORDER BY e.id DESC LIMIT 1;
  prev := COALESCE(prev, repeat('0', 64));
  h := encode(sha256(convert_to(concat_ws('|', prev, p_tenant, left(p_actor, 255), left(p_action, 64),
         left(p_type, 32), left(p_resource, 400), left(COALESCE(p_detail, ''), 2000),
         to_char(ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS')), 'UTF8')), 'hex');
  INSERT INTO ide_audit_events(tenant_id, actor, action, resource_type, resource_id, detail, prev_hash, hash, created_at)
  VALUES (p_tenant, left(p_actor, 255), left(p_action, 64), left(p_type, 32), left(p_resource, 400),
          left(COALESCE(p_detail, ''), 2000), prev, h, ts);
  RETURN h;
END;
$$;

-- Verifies the caller's tenant chain: returns the id of the first broken event, or NULL if intact.
CREATE OR REPLACE FUNCTION ide_verify_audit(p_tenant VARCHAR)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE r RECORD; prev CHAR(64) := repeat('0', 64);
BEGIN
  IF p_tenant IS DISTINCT FROM NULLIF(current_setting('ide.tenant_id', true), '') THEN
    RAISE EXCEPTION 'audit tenant mismatch' USING ERRCODE = '42501';
  END IF;
  FOR r IN SELECT * FROM ide_audit_events WHERE tenant_id = p_tenant ORDER BY id LOOP
    IF r.prev_hash <> prev OR r.hash <> encode(sha256(convert_to(concat_ws('|', r.prev_hash, r.tenant_id,
         r.actor, r.action, r.resource_type, r.resource_id, r.detail,
         to_char(r.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS')), 'UTF8')), 'hex') THEN
      RETURN r.id;
    END IF;
    prev := r.hash;
  END LOOP;
  RETURN NULL;
END;
$$;

-- §5 membership management without giving the runtime role INSERT/UPDATE on memberships.
-- Owners/admins manage members; only owners grant or change owners; the last owner stays.
CREATE OR REPLACE FUNCTION ide_set_member_role(p_tenant VARCHAR, p_actor VARCHAR,
                                               p_subject VARCHAR, p_role VARCHAR)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE actor_role VARCHAR; target_role VARCHAR; owners INTEGER;
BEGIN
  IF p_tenant IS DISTINCT FROM NULLIF(current_setting('ide.tenant_id', true), '') THEN
    RAISE EXCEPTION 'tenant mismatch' USING ERRCODE = '42501';
  END IF;
  IF p_subject IS NULL OR length(p_subject) NOT BETWEEN 1 AND 255
     OR p_role NOT IN ('owner','admin','editor','media_editor','reviewer','viewer','remove') THEN
    RAISE EXCEPTION 'invalid member change' USING ERRCODE = '22023';
  END IF;
  SELECT role INTO actor_role FROM ide_memberships WHERE tenant_id = p_tenant AND subject = p_actor;
  IF actor_role IS NULL OR actor_role NOT IN ('owner','admin') THEN
    RAISE EXCEPTION 'only owners and admins manage members' USING ERRCODE = '42501';
  END IF;
  SELECT role INTO target_role FROM ide_memberships WHERE tenant_id = p_tenant AND subject = p_subject FOR UPDATE;
  IF (p_role = 'owner' OR target_role = 'owner') AND actor_role <> 'owner' THEN
    RAISE EXCEPTION 'only owners grant or change owners' USING ERRCODE = '42501';
  END IF;
  IF target_role = 'owner' AND p_role <> 'owner' THEN
    SELECT count(*) INTO owners FROM ide_memberships WHERE tenant_id = p_tenant AND role = 'owner';
    IF owners <= 1 THEN
      RAISE EXCEPTION 'a workspace needs at least one owner' USING ERRCODE = '23514';
    END IF;
  END IF;
  IF p_role = 'remove' THEN
    DELETE FROM ide_memberships WHERE tenant_id = p_tenant AND subject = p_subject;
  ELSE
    INSERT INTO ide_memberships(tenant_id, subject, role) VALUES (p_tenant, p_subject, p_role)
    ON CONFLICT (tenant_id, subject) DO UPDATE SET role = EXCLUDED.role;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION ide_append_audit(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION ide_verify_audit(VARCHAR) FROM PUBLIC;
REVOKE ALL ON FUNCTION ide_set_member_role(VARCHAR, VARCHAR, VARCHAR, VARCHAR) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ide_runtime') THEN
    GRANT EXECUTE ON FUNCTION ide_append_audit(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, TEXT) TO ide_runtime;
    GRANT EXECUTE ON FUNCTION ide_verify_audit(VARCHAR) TO ide_runtime;
    GRANT EXECUTE ON FUNCTION ide_set_member_role(VARCHAR, VARCHAR, VARCHAR, VARCHAR) TO ide_runtime;
    GRANT SELECT, INSERT ON ide_file_versions TO ide_runtime;
    GRANT SELECT ON ide_audit_events TO ide_runtime;
    GRANT DELETE ON ide_workspace_files TO ide_runtime;
  END IF;
END $$;
