-- Authoritative identity records must be maintained only by a trusted IdP sync.
CREATE SCHEMA IF NOT EXISTS hitl;
CREATE TABLE IF NOT EXISTS hitl.identity_memberships (
 tenant_id uuid NOT NULL,
 subject text NOT NULL CHECK (length(subject) BETWEEN 8 AND 128),
 issuer text NOT NULL CHECK (issuer LIKE 'https://%'),
 active boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,subject,issuer)
);
CREATE TABLE IF NOT EXISTS hitl.identity_revocations (
 tenant_id uuid NOT NULL,
 subject text NOT NULL CHECK (length(subject) BETWEEN 8 AND 128),
 issuer text NOT NULL CHECK (issuer LIKE 'https://%'),
 token_id text NOT NULL CHECK (length(token_id) BETWEEN 8 AND 256),
 revoked_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,subject,issuer,token_id)
);
REVOKE ALL ON hitl.identity_memberships FROM PUBLIC;
REVOKE ALL ON hitl.identity_revocations FROM PUBLIC;
-- Grant SELECT only to a dedicated restricted identity-check role.
-- Grant writes only to the trusted identity synchronizer. Never grant
-- identity mutation permissions to the HITL HTTP service role.
