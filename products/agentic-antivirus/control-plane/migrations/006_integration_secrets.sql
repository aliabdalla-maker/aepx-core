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
