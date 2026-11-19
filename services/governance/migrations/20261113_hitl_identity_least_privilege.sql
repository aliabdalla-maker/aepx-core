-- Apply ONLY after review, on isolated staging, as an administrator.
-- Idempotent restricted identities for authoritative HITL records.
-- NO LOGIN roles: attach dedicated LOGIN principals with separately managed
-- credentials through approved infrastructure provisioning.
BEGIN;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aepx_hitl_identity_reader') THEN
    CREATE ROLE aepx_hitl_identity_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aepx_hitl_identity_publisher') THEN
    CREATE ROLE aepx_hitl_identity_publisher NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END $$;
REVOKE ALL ON SCHEMA hitl FROM PUBLIC;
REVOKE ALL ON TABLE hitl.identity_memberships,hitl.identity_revocations,
  hitl.identity_authority_sync FROM PUBLIC;
GRANT USAGE ON SCHEMA hitl TO aepx_hitl_identity_reader,aepx_hitl_identity_publisher;
GRANT SELECT ON TABLE hitl.identity_memberships,hitl.identity_revocations,
  hitl.identity_authority_sync TO aepx_hitl_identity_reader;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE hitl.identity_memberships,
  hitl.identity_revocations TO aepx_hitl_identity_publisher;
GRANT SELECT,INSERT,UPDATE ON TABLE hitl.identity_authority_sync
  TO aepx_hitl_identity_publisher;
-- Explicitly prohibit write access through the reader role.
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON TABLE
  hitl.identity_memberships,hitl.identity_revocations,hitl.identity_authority_sync
  FROM aepx_hitl_identity_reader;
-- Restrict publisher from schema changes and table truncation.
REVOKE CREATE ON SCHEMA hitl FROM aepx_hitl_identity_reader,aepx_hitl_identity_publisher;
REVOKE TRUNCATE,REFERENCES,TRIGGER ON TABLE
  hitl.identity_memberships,hitl.identity_revocations,hitl.identity_authority_sync
  FROM aepx_hitl_identity_publisher;
COMMIT;
