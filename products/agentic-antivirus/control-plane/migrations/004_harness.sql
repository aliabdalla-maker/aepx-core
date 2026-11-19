-- 004: defensive cybersecurity agentic harness (deployment prompt §3C) and live rollout evidence (§3D).
-- Additive only: build 0.1.2 keeps working on this schema, so a rollback needs no restore.

-- Action requests carry the full request contract and an explicit lifecycle (§3C runtime and tool contracts).
ALTER TABLE aav.action_requests
  ADD COLUMN IF NOT EXISTS lifecycle text NOT NULL DEFAULT 'proposed'
    CHECK (lifecycle IN ('proposed', 'awaiting_approval', 'queued', 'running', 'verification_pending', 'verified',
                         'failed', 'denied', 'expired', 'manual_reconciliation')),
  ADD COLUMN IF NOT EXISTS lifecycle_reason text,
  ADD COLUMN IF NOT EXISTS idempotency_key text,
  ADD COLUMN IF NOT EXISTS expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS policy_version text,
  ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS runtime_mode text CHECK (runtime_mode IN ('simulation', 'observe', 'respond')),
  ADD COLUMN IF NOT EXISTS drill boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS verified_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS action_requests_idem ON aav.action_requests (tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS action_requests_lifecycle ON aav.action_requests (tenant_id, lifecycle, created_at);

-- Existing rows: derive the lifecycle from the old status so history reads correctly.
UPDATE aav.action_requests SET lifecycle = CASE status
  WHEN 'proposed' THEN 'awaiting_approval' WHEN 'approved' THEN 'queued' WHEN 'denied' THEN 'denied'
  WHEN 'dispatched' THEN 'running' WHEN 'completed' THEN 'verification_pending' WHEN 'failed' THEN 'failed'
  WHEN 'expired' THEN 'expired' ELSE 'proposed' END,
  lifecycle_reason = 'recorded before the harness: receipt only, no independent verification'
WHERE lifecycle = 'proposed' AND runtime_mode IS NULL;

-- Approvals record who approved with which roles; one-time use already exists (used_at).
ALTER TABLE aav.approvals ADD COLUMN IF NOT EXISTS approver_roles jsonb NOT NULL DEFAULT '[]'::jsonb;

-- Dispatch attempts: written and committed before an adapter is called, so a worker that dies after
-- dispatch leaves a record that is reconciled against the provider before any retry.
CREATE TABLE IF NOT EXISTS aav.action_dispatches (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  action_request_id   uuid NOT NULL REFERENCES aav.action_requests(id) ON DELETE CASCADE,
  attempt             integer NOT NULL,
  adapter             text NOT NULL,
  provider_request_id text NOT NULL,
  state               text NOT NULL DEFAULT 'running'
                      CHECK (state IN ('running', 'receipted', 'failed', 'not_executed', 'unknown')),
  lease_owner         text NOT NULL,
  lease_expires_at    timestamptz NOT NULL,
  receipt             jsonb,
  error               text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (action_request_id, attempt)
);

-- Independent verification: read-only probes the agent answers on a later heartbeat, separate from the
-- command path, or server-side checks (scan jobs, definitions version, stored rows).
CREATE TABLE IF NOT EXISTS aav.action_verifications (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  action_request_id uuid NOT NULL REFERENCES aav.action_requests(id) ON DELETE CASCADE,
  device_id         uuid REFERENCES aav.devices(id) ON DELETE CASCADE,
  probe             text NOT NULL CHECK (probe IN ('isolation_active', 'pid_absent', 'path_absent', 'vault_contains',
                                                   'vault_absent', 'scan_job_complete', 'definitions_version',
                                                   'row_present', 'metadata_received', 'provider_status', 'simulated')),
  args              jsonb NOT NULL DEFAULT '{}'::jsonb,
  expect            jsonb NOT NULL,
  status            text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'passed', 'failed', 'expired')),
  observed          jsonb,
  source            text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  observed_at       timestamptz,
  expires_at        timestamptz NOT NULL DEFAULT now() + interval '24 hours'
);
CREATE INDEX IF NOT EXISTS action_verifications_pending ON aav.action_verifications (device_id) WHERE status = 'pending';

-- Signal-to-triage time (§3C KPIs).
ALTER TABLE aav.incidents ADD COLUMN IF NOT EXISTS triaged_at timestamptz;

-- Production assertions (§3D "Live console and production evidence").
CREATE TABLE IF NOT EXISTS aav.production_assertions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  requirement_id  text NOT NULL,
  environment     text NOT NULL,
  scope           text NOT NULL,              -- asset, cohort or endpoint
  artefact_digest text NOT NULL,
  policy_version  text NOT NULL,
  outcome         text NOT NULL CHECK (outcome IN ('PASS', 'FAIL', 'BLOCKED', 'NOT RUN', 'N/A')),
  coverage        text NOT NULL DEFAULT 'observe' CHECK (coverage IN ('observe', 'respond', 'drill')),
  evidence        text NOT NULL,
  owner           text NOT NULL,
  note            text NOT NULL DEFAULT '',
  recorded_by     text NOT NULL,
  observed_at     timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['action_dispatches', 'action_verifications', 'production_assertions'] LOOP
    EXECUTE format('ALTER TABLE aav.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE aav.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON aav.%I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON aav.%I USING (tenant_id = aav.current_tenant()) '
                   'WITH CHECK (tenant_id = aav.current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON aav.%I TO aav_app', t);
  END LOOP;
END $$;
-- Assertions are evidence: no update or delete for the application role.
REVOKE UPDATE ON aav.production_assertions FROM aav_app;

-- Ingestion retention (§3C "apply retention"): events older than each tenant's privacy.telemetry_retention_days
-- (default 90) are deleted. Definer so one platform job can apply every tenant's own setting.
CREATE OR REPLACE FUNCTION aav.apply_telemetry_retention()
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
DECLARE n bigint;
BEGIN
  WITH policy AS (
    SELECT t.id AS tenant_id,
           GREATEST(coalesce((SELECT (s.value #>> '{}')::int FROM aav.settings s
                              WHERE s.tenant_id = t.id AND s.category = 'privacy' AND s.key = 'telemetry_retention_days'),
                             90), 7) AS days
    FROM aav.tenants t)
  DELETE FROM aav.events e USING policy p
  WHERE e.tenant_id = p.tenant_id AND e.occurred_at < now() - make_interval(days => p.days)
    AND NOT EXISTS (SELECT 1 FROM aav.alerts a WHERE e.id = ANY(a.evidence_event_ids));
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION aav.apply_telemetry_retention() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.apply_telemetry_retention() TO aav_app;
