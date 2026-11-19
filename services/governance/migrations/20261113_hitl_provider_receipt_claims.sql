-- AEP-X signed provider receipt replay claims.
-- Apply with privileged migration identity; use a non-owner runtime role.
-- Globally unique provider/receipt_id prevents replay across tenants.
CREATE SCHEMA IF NOT EXISTS hitl;
CREATE TABLE IF NOT EXISTS hitl.provider_receipt_claims (
    provider text NOT NULL CHECK (length(provider) BETWEEN 8 AND 128),
    receipt_id text NOT NULL CHECK (length(receipt_id) BETWEEN 8 AND 128),
    claimed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, receipt_id)
);
REVOKE ALL ON hitl.provider_receipt_claims FROM PUBLIC;
-- Grant only INSERT and SELECT of receipt_id to the dedicated replay
-- service role after provisioning it; never grant UPDATE or DELETE.
-- Runtime role must not own this table or have superuser/BYPASSRLS.
