-- Self-service sign-up: a verified user may create exactly one private workspace for
-- themselves. The runtime role keeps SELECT-only access to ide_memberships and gets this
-- narrow function instead of INSERT, so it can never add members to an existing workspace.
-- Apply as the migration role.
CREATE OR REPLACE FUNCTION ide_open_personal_workspace(p_tenant VARCHAR, p_subject VARCHAR)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF p_tenant !~ '^u-[0-9a-f]{32}$' OR p_subject IS NULL OR length(p_subject) NOT BETWEEN 1 AND 255 THEN
    RAISE EXCEPTION 'invalid personal workspace' USING ERRCODE = '22023';
  END IF;
  IF EXISTS (SELECT 1 FROM ide_memberships WHERE tenant_id = p_tenant AND subject <> p_subject) THEN
    RAISE EXCEPTION 'workspace belongs to another user' USING ERRCODE = '42501';
  END IF;
  INSERT INTO ide_memberships (tenant_id, subject, role)
  VALUES (p_tenant, p_subject, 'owner')
  ON CONFLICT (tenant_id, subject) DO NOTHING;
END;
$$;
REVOKE ALL ON FUNCTION ide_open_personal_workspace(VARCHAR, VARCHAR) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ide_runtime') THEN
    GRANT EXECUTE ON FUNCTION ide_open_personal_workspace(VARCHAR, VARCHAR) TO ide_runtime;
  END IF;
END $$;
