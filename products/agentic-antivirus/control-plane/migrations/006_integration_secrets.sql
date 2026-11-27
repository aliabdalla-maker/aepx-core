-- B-06 live provider adapters: write-only, encrypted integration credentials (AES-256-GCM, see app/crypto.py).
CREATE TABLE aav.integration_secrets (
  integration_id uuid PRIMARY KEY REFERENCES aav.integrations(id) ON DELETE CASCADE,
  tenant_id      uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  nonce          bytea NOT NULL,
  ciphertext     bytea NOT NULL,
  updated_by     text NOT NULL,
  updated_at     timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE aav.integration_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE aav.integration_secrets FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON aav.integration_secrets USING (tenant_id = aav.current_tenant())
  WITH CHECK (tenant_id = aav.current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON aav.integration_secrets TO aav_app;

-- INT-02 pull transports (SQL, IMAP): the poller runs without a tenant context and needs the list of enabled
-- pull integrations across tenants. Definer function, minimal columns, never the webhook hash.
CREATE OR REPLACE FUNCTION aav.pollable_integrations()
RETURNS TABLE (id uuid, tenant_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT id, tenant_id FROM aav.integrations
  WHERE enabled AND maturity IN ('verified_live', 'test_only') AND protocol IN ('sql', 'imap')
$$;
REVOKE ALL ON FUNCTION aav.pollable_integrations() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.pollable_integrations() TO aav_app;
