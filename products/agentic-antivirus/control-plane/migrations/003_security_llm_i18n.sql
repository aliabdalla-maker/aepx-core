-- Release 1 (AEP-X deployment prompt §3, 3A, 3B): scan jobs, device posture, network visibility,
-- security gaps, recovery removal states, LLM usage accounting and the translation store.

-- SEC-01: every scan is a job with scope, progress, coverage gaps and an outcome.
CREATE TABLE aav.scan_jobs (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  device_id        uuid NOT NULL REFERENCES aav.devices(id) ON DELETE CASCADE,
  scan_type        text NOT NULL CHECK (scan_type IN ('quick', 'full', 'targeted', 'scheduled', 'on_demand', 'recovery')),
  scope            jsonb NOT NULL DEFAULT '[]'::jsonb,
  status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'complete', 'partial',
                     'failed', 'cancelled', 'timed_out', 'missed')),
  cancel_requested boolean NOT NULL DEFAULT false,
  max_seconds      integer NOT NULL DEFAULT 3600 CHECK (max_seconds BETWEEN 10 AND 86400),
  files_scanned    integer NOT NULL DEFAULT 0,
  archives_scanned integer NOT NULL DEFAULT 0,
  detections       integer NOT NULL DEFAULT 0,
  gaps             jsonb NOT NULL DEFAULT '{}'::jsonb,
  engine_version   text,
  incident_id      uuid REFERENCES aav.incidents(id) ON DELETE SET NULL,
  requested_by     text NOT NULL,
  group_id         uuid NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  started_at       timestamptz,
  finished_at      timestamptz,
  progress_at      timestamptz
);
CREATE INDEX scan_jobs_device ON aav.scan_jobs (device_id, created_at DESC);
CREATE INDEX scan_jobs_group ON aav.scan_jobs (group_id, device_id);

-- SEC-05: device posture reported by the agent (null = not observable on this platform = Unknown).
ALTER TABLE aav.devices ADD COLUMN posture jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE aav.devices ADD COLUMN posture_at timestamptz;
ALTER TABLE aav.devices ADD COLUMN definitions_installed_at timestamptz;
ALTER TABLE aav.devices ADD COLUMN in_scope boolean NOT NULL DEFAULT true;
ALTER TABLE aav.devices ADD COLUMN site text NOT NULL DEFAULT '';

-- SEC-04: network segments in the authorised asset inventory and their telemetry freshness.
CREATE TABLE aav.network_segments (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  name              text NOT NULL,
  cidr              cidr NOT NULL,
  site              text NOT NULL DEFAULT '',
  in_scope          boolean NOT NULL DEFAULT true,
  telemetry_source  text,
  last_telemetry_at timestamptz,
  owner             text NOT NULL DEFAULT '',
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, cidr)
);

-- SEC-04: exposure inventory from approved sources (deduplicated by kind + value).
CREATE TABLE aav.network_assets (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  kind         text NOT NULL CHECK (kind IN ('host', 'service', 'certificate')),
  value        text NOT NULL,
  segment_id   uuid REFERENCES aav.network_segments(id) ON DELETE SET NULL,
  attributes   jsonb NOT NULL DEFAULT '{}'::jsonb,
  source       text NOT NULL,
  first_seen   timestamptz NOT NULL DEFAULT now(),
  last_seen    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, kind, value)
);

-- Scan KPI and gap dashboard: every gap row carries the prompt's mandatory fields.
CREATE TABLE aav.security_gaps (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  subject_kind     text NOT NULL CHECK (subject_kind IN ('device', 'segment', 'endpoint', 'exclusion', 'integration')),
  subject_id       text NOT NULL,
  subject_label    text NOT NULL,
  expected_control text NOT NULL,
  observed_state   text NOT NULL,
  last_evidence_at timestamptz,
  reason           text NOT NULL,
  severity         text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  owner            text NOT NULL DEFAULT '',
  due_date         date NOT NULL,
  proposed_fix     text NOT NULL,
  retest_status    text NOT NULL DEFAULT 'not_retested' CHECK (retest_status IN ('not_retested', 'retest_failed',
                     'verified_closed')),
  status           text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  opened_at        timestamptz NOT NULL DEFAULT now(),
  closed_at        timestamptz,
  closed_evidence  jsonb,
  UNIQUE (tenant_id, subject_kind, subject_id, expected_control, status, opened_at)
);
CREATE UNIQUE INDEX security_gaps_one_open ON aav.security_gaps (tenant_id, subject_kind, subject_id, expected_control)
  WHERE status = 'open';

-- Exclusions carry an expiry and an approver (gap dashboard: reason, expiry, approval).
ALTER TABLE aav.exclusions ADD COLUMN expires_at timestamptz;
ALTER TABLE aav.exclusions ADD COLUMN approved_by uuid REFERENCES aav.users(id);

-- REC-03..06: removal state per detection and the recurrence watch.
ALTER TABLE aav.recovery_items ADD COLUMN detection_ref text;
ALTER TABLE aav.recovery_items ADD COLUMN removal_state text
  CHECK (removal_state IN ('quarantined', 'removed', 'removal_failed', 'reimage_required', 'pending_verification'));
ALTER TABLE aav.recovery_items ADD COLUMN removal_verified_at timestamptz;
ALTER TABLE aav.recovery_items ADD COLUMN verification_scan_id uuid REFERENCES aav.scan_jobs(id);
ALTER TABLE aav.recovery_items ADD COLUMN mitigation jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE aav.recovery_items ADD COLUMN observation_until timestamptz;
ALTER TABLE aav.recovery_items ADD COLUMN recurred_at timestamptz;
ALTER TABLE aav.recovery_items ADD COLUMN confirmed_infected_at timestamptz;
ALTER TABLE aav.recovery_items ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();

-- LLM calls: provider, model, purpose, tokens and cost per tenant (spend caps, cost per verified success).
CREATE TABLE aav.llm_usage (
  id            bigserial PRIMARY KEY,
  tenant_id     uuid REFERENCES aav.tenants(id) ON DELETE CASCADE,
  provider      text NOT NULL,
  model         text NOT NULL,
  purpose       text NOT NULL,
  input_tokens  integer NOT NULL DEFAULT 0,
  output_tokens integer NOT NULL DEFAULT 0,
  cost_usd      numeric(12, 6) NOT NULL DEFAULT 0,
  ok            boolean NOT NULL,
  latency_ms    integer NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX llm_usage_month ON aav.llm_usage (created_at);

-- Translations of the shared UI catalogue (global, not tenant data). Machine output is labelled
-- until a reviewer approves it (L10N-11, L10N-12).
CREATE TABLE aav.translations (
  locale      text NOT NULL,
  msg_key     text NOT NULL,
  source_hash text NOT NULL,
  text        text NOT NULL,
  origin      text NOT NULL CHECK (origin IN ('human', 'machine:catalogue', 'machine:llm')),
  provider    text NOT NULL DEFAULT '',
  reviewed_by uuid REFERENCES aav.users(id),
  reviewed_at timestamptz,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (locale, msg_key)
);
GRANT SELECT, INSERT, UPDATE ON aav.translations TO aav_app;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['scan_jobs', 'network_segments', 'network_assets', 'security_gaps'] LOOP
    EXECUTE format('ALTER TABLE aav.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE aav.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON aav.%I USING (tenant_id = aav.current_tenant()) '
                   'WITH CHECK (tenant_id = aav.current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON aav.%I TO aav_app', t);
  END LOOP;
END $$;

-- LLM usage: tenant rows isolated; platform rows (tenant_id NULL, e.g. catalogue translation) only
-- without a tenant context. Insert + read, never update or delete (cost evidence).
ALTER TABLE aav.llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE aav.llm_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY llm_usage_read ON aav.llm_usage FOR SELECT USING (tenant_id IS NOT DISTINCT FROM aav.current_tenant());
CREATE POLICY llm_usage_insert ON aav.llm_usage FOR INSERT WITH CHECK (tenant_id IS NOT DISTINCT FROM aav.current_tenant());
GRANT SELECT, INSERT ON aav.llm_usage TO aav_app;
GRANT USAGE ON SEQUENCE aav.llm_usage_id_seq TO aav_app;

-- Platform-wide spend this month (all tenants) for the global cap; definer because RLS hides other tenants.
CREATE OR REPLACE FUNCTION aav.llm_spend_this_month(p_provider text)
RETURNS numeric
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT coalesce(sum(cost_usd), 0) FROM aav.llm_usage
  WHERE provider = p_provider AND created_at >= date_trunc('month', now())
$$;
REVOKE ALL ON FUNCTION aav.llm_spend_this_month(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.llm_spend_this_month(text) TO aav_app;
