-- Run as privileged migration role; never as the runtime role.
-- User-level (not tenant-level) entitlements: a £4.99/month subscription belongs to the
-- authenticated OIDC subject. Store webhooks carry no tenant context, so these tables are not
-- tenant-RLS scoped; application code only ever reads/writes the caller's own subject row,
-- and webhooks locate rows by the opaque account_id bound at purchase time.
CREATE TABLE IF NOT EXISTS ide_entitlements (
  subject VARCHAR(255) PRIMARY KEY,
  account_id UUID NOT NULL UNIQUE,
  trial_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source VARCHAR(16) CHECK (source IN ('stripe','google_play','app_store')),
  status VARCHAR(16) NOT NULL DEFAULT 'none'
    CHECK (status IN ('none','active','grace','canceled','expired','revoked')),
  current_period_end TIMESTAMPTZ,
  external_ref VARCHAR(255),
  customer_ref VARCHAR(255), -- Stripe customer id, for the self-service cancellation portal
  last_event_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ide_entitlements_external
  ON ide_entitlements(source, external_ref) WHERE external_ref IS NOT NULL;

-- Idempotency ledger: every provider event/notification is processed at most once.
CREATE TABLE IF NOT EXISTS ide_billing_events (
  provider VARCHAR(16) NOT NULL CHECK (provider IN ('stripe','google_play','app_store')),
  event_id VARCHAR(255) NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (provider, event_id)
);
