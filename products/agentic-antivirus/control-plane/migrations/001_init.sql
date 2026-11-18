-- Agentic Antivirus control plane schema.
-- Trace: BE-02, BE-03 (RLS), ARC-02, FN-02, AX-10, RA-08.
-- Tenant isolation: every tenant-scoped table has FORCE ROW LEVEL SECURITY and a policy
-- bound to the per-transaction setting aav.tenant_id. The application connects as
-- aav_app, which is not a superuser and has no BYPASSRLS, so a missing tenant context
-- returns no rows (fail closed).

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS aav;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aav_app') THEN
    CREATE ROLE aav_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

GRANT USAGE ON SCHEMA aav TO aav_app;

CREATE OR REPLACE FUNCTION aav.current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('aav.tenant_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------- global identity
CREATE TABLE aav.tenants (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  parent_msp_id uuid REFERENCES aav.tenants(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.users (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text NOT NULL UNIQUE CHECK (email = lower(email) AND position('@' in email) > 1),
  password_hash  text,
  oidc_subject   text UNIQUE,
  email_verified boolean NOT NULL DEFAULT false,
  display_name   text NOT NULL DEFAULT '',
  locale         text NOT NULL DEFAULT 'en',
  failed_logins  integer NOT NULL DEFAULT 0,
  locked_until   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  deleted_at     timestamptz
);

CREATE TABLE aav.auth_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES aav.users(id) ON DELETE CASCADE,
  kind        text NOT NULL CHECK (kind IN ('email_verify', 'password_reset', 'invite')),
  token_hash  text NOT NULL UNIQUE,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES aav.users(id) ON DELETE CASCADE,
  token_hash  text NOT NULL UNIQUE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz
);

-- Outbound mail queue (verification / reset links). Delivery needs an SMTP integration;
-- until one is verified the rows stay queued and are never reported as sent.
CREATE TABLE aav.outbound_mail (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  to_email    text NOT NULL,
  template    text NOT NULL,
  payload     jsonb NOT NULL,
  status      text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed')),
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- tenant scoped
CREATE TABLE aav.memberships (
  tenant_id  uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES aav.users(id) ON DELETE CASCADE,
  role       text NOT NULL CHECK (role IN ('tenant_admin', 'it_admin', 'security_analyst',
                                          'endpoint_user', 'auditor', 'msp_operator')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id, role)
);

CREATE TABLE aav.policies (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  name        text NOT NULL,
  version     integer NOT NULL,
  body        jsonb NOT NULL,
  signature   text NOT NULL,
  key_id      text NOT NULL,
  created_by  uuid REFERENCES aav.users(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name, version)
);

CREATE TABLE aav.devices (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  hostname             text NOT NULL,
  os                   text NOT NULL CHECK (os IN ('windows', 'macos', 'linux', 'android', 'ios')),
  os_version           text NOT NULL DEFAULT '',
  agent_version        text NOT NULL DEFAULT '',
  device_key_hash      text NOT NULL UNIQUE,
  owner_user_id        uuid REFERENCES aav.users(id),
  criticality          text NOT NULL DEFAULT 'standard' CHECK (criticality IN ('standard', 'critical')),
  policy_name          text,
  applied_policy_version integer,
  definitions_version  text,
  sensor_health        jsonb NOT NULL DEFAULT '{}'::jsonb,
  protection_status    text NOT NULL DEFAULT 'unknown'
                       CHECK (protection_status IN ('protected', 'degraded', 'disabled', 'unknown')),
  isolation_state      text NOT NULL DEFAULT 'none' CHECK (isolation_state IN ('none', 'isolated')),
  isolation_expires_at timestamptz,
  enrolled_at          timestamptz NOT NULL DEFAULT now(),
  last_seen_at         timestamptz,
  retired_at           timestamptz
);

CREATE TABLE aav.enrollment_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  token_hash  text NOT NULL UNIQUE,
  max_uses    integer NOT NULL CHECK (max_uses > 0),
  uses        integer NOT NULL DEFAULT 0,
  expires_at  timestamptz NOT NULL,
  created_by  uuid REFERENCES aav.users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.events (
  id          bigserial PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  device_id   uuid NOT NULL REFERENCES aav.devices(id) ON DELETE CASCADE,
  event_uid   text NOT NULL,
  kind        text NOT NULL,
  occurred_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  data        jsonb NOT NULL,
  UNIQUE (device_id, event_uid)
);
CREATE INDEX events_tenant_time ON aav.events (tenant_id, occurred_at DESC);

CREATE TABLE aav.incidents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  title       text NOT NULL,
  severity    text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  status      text NOT NULL DEFAULT 'open'
              CHECK (status IN ('open', 'investigating', 'contained', 'recovering', 'resolved')),
  category    text NOT NULL DEFAULT 'endpoint',
  assignee    uuid REFERENCES aav.users(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.alerts (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  device_id         uuid REFERENCES aav.devices(id) ON DELETE CASCADE,
  source            text NOT NULL DEFAULT 'endpoint',
  severity          text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  title             text NOT NULL,
  rule_id           text NOT NULL,
  rule_version      text NOT NULL,
  technique         text,
  detected_at       timestamptz NOT NULL,
  published_at      timestamptz NOT NULL DEFAULT now(),
  evidence_event_ids bigint[] NOT NULL DEFAULT '{}',
  evidence          jsonb NOT NULL DEFAULT '{}'::jsonb,
  action_taken      text,
  status            text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'triaged', 'false_positive', 'closed')),
  incident_id       uuid REFERENCES aav.incidents(id)
);
CREATE INDEX alerts_tenant_time ON aav.alerts (tenant_id, detected_at DESC);

CREATE TABLE aav.quarantine_items (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  device_id      uuid NOT NULL REFERENCES aav.devices(id) ON DELETE CASCADE,
  local_id       text NOT NULL,
  sha256         text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  original_path  text NOT NULL,
  detection      text NOT NULL,
  rule_version   text NOT NULL,
  quarantined_at timestamptz NOT NULL,
  status         text NOT NULL DEFAULT 'quarantined'
                 CHECK (status IN ('quarantined', 'review_requested', 'restore_approved', 'restored', 'deleted')),
  review_reason  text,
  reviewed_by    uuid REFERENCES aav.users(id),
  restore_scan   jsonb,
  UNIQUE (device_id, local_id)
);

CREATE TABLE aav.exclusions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  kind        text NOT NULL CHECK (kind IN ('path', 'sha256')),
  value       text NOT NULL,
  reason      text NOT NULL CHECK (length(reason) >= 3),
  created_by  uuid NOT NULL REFERENCES aav.users(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, kind, value)
);

CREATE TABLE aav.scan_schedules (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  policy_name text NOT NULL,
  scan_type   text NOT NULL CHECK (scan_type IN ('quick', 'full')),
  cron        text NOT NULL,
  created_by  uuid REFERENCES aav.users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.action_requests (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  incident_id    uuid REFERENCES aav.incidents(id),
  action_type    text NOT NULL,
  targets        jsonb NOT NULL,
  targets_digest text NOT NULL,
  params         jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason         text NOT NULL DEFAULT '',
  proposed_by    text NOT NULL,          -- 'user:<uuid>' | 'ai:investigator' | 'policy:auto'
  status         text NOT NULL DEFAULT 'proposed'
                 CHECK (status IN ('proposed', 'approved', 'denied', 'dispatched', 'completed', 'failed', 'expired')),
  policy_decision jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.approvals (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  action_request_id uuid NOT NULL REFERENCES aav.action_requests(id) ON DELETE CASCADE,
  approver_id      uuid NOT NULL REFERENCES aav.users(id),
  action_type      text NOT NULL,
  targets_digest   text NOT NULL,
  expires_at       timestamptz NOT NULL,
  used_at          timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.commands (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  device_id        uuid NOT NULL REFERENCES aav.devices(id) ON DELETE CASCADE,
  action_request_id uuid REFERENCES aav.action_requests(id),
  idempotency_key  text NOT NULL,
  command_type     text NOT NULL,
  params           jsonb NOT NULL,
  envelope         jsonb NOT NULL,
  signature        text NOT NULL,
  issued_at        timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz NOT NULL,
  status           text NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'delivered', 'acknowledged', 'failed', 'expired')),
  ack_at           timestamptz,
  result           jsonb,
  UNIQUE (device_id, idempotency_key)
);

CREATE TABLE aav.notifications (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  user_id     uuid REFERENCES aav.users(id) ON DELETE CASCADE,
  kind        text NOT NULL,
  title       text NOT NULL,
  body        jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  read_at     timestamptz
);

CREATE TABLE aav.investigations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  incident_id  uuid NOT NULL REFERENCES aav.incidents(id) ON DELETE CASCADE,
  engine       text NOT NULL,           -- 'rules' or 'llm:<provider>'
  findings     jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- integrations / threat coverage
CREATE TABLE aav.integrations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  name        text NOT NULL,
  signal_kind text NOT NULL CHECK (signal_kind IN ('identity', 'dns', 'firewall', 'waf', 'api_gateway', 'ddos',
                 'cdn', 'load_balancer', 'backup', 'dlp', 'cloud_audit', 'email', 'url_reputation', 'physical',
                 'vulnerability', 'smtp', 'other')),
  protocol    text NOT NULL CHECK (protocol IN ('rest', 'openapi', 'graphql', 'grpc', 'mcp', 'webhook', 'oauth2',
                 'oidc', 'smtp', 'imap', 'sftp', 'amqp', 'mqtt', 'sql')),
  endpoint    text NOT NULL DEFAULT '',
  config      jsonb NOT NULL DEFAULT '{}'::jsonb,
  secret_ref  text,                     -- reference into the runtime secret store, never the secret
  webhook_secret_hash text,
  maturity    text NOT NULL DEFAULT 'unavailable'
              CHECK (maturity IN ('verified_live', 'test_only', 'stub', 'unavailable')),
  enabled     boolean NOT NULL DEFAULT false,
  public_port_approved boolean NOT NULL DEFAULT false,
  last_health jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE aav.external_alerts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  integration_id uuid NOT NULL REFERENCES aav.integrations(id) ON DELETE CASCADE,
  signal_kind   text NOT NULL,
  category      text NOT NULL,
  severity      text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  asset         text,
  device_id     uuid REFERENCES aav.devices(id),
  user_ref      text,
  confirmed     boolean NOT NULL DEFAULT false,
  external_id   text NOT NULL,
  observed_at   timestamptz NOT NULL,
  received_at   timestamptz NOT NULL DEFAULT now(),
  notified_at   timestamptz,
  data          jsonb NOT NULL,
  incident_id   uuid REFERENCES aav.incidents(id),
  UNIQUE (integration_id, external_id)
);

CREATE TABLE aav.protected_assets (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  kind                 text NOT NULL CHECK (kind IN ('ip', 'hostname', 'dns_zone')),
  value                text NOT NULL,
  service              text NOT NULL,
  service_owner        text NOT NULL DEFAULT '',
  provider             text,
  mitigation_policy    text,
  capacity_assumptions text,
  exception_note       text,
  public               boolean NOT NULL DEFAULT true,
  mitigation_active    boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, kind, value)
);

CREATE TABLE aav.service_objectives (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  service            text NOT NULL,
  availability_pct   numeric(6,3) NOT NULL CHECK (availability_pct > 0 AND availability_pct <= 100),
  latency_p95_ms     integer NOT NULL CHECK (latency_p95_ms > 0),
  success_rate_pct   numeric(6,3) NOT NULL CHECK (success_rate_pct > 0 AND success_rate_pct <= 100),
  UNIQUE (tenant_id, service)
);

CREATE TABLE aav.traffic_policies (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  service        text NOT NULL,
  control        text NOT NULL CHECK (control IN ('rate_limit', 'bot_control', 'challenge', 'cache', 'geo_block', 'ip_block')),
  config         jsonb NOT NULL,
  customer_impacting boolean NOT NULL DEFAULT true,
  standing       boolean NOT NULL DEFAULT false,
  status         text NOT NULL DEFAULT 'proposed'
                 CHECK (status IN ('proposed', 'approved', 'active', 'rolled_back', 'rejected')),
  action_request_id uuid REFERENCES aav.action_requests(id),
  version        integer NOT NULL DEFAULT 1,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.recovery_items (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  incident_id     uuid NOT NULL REFERENCES aav.incidents(id) ON DELETE CASCADE,
  device_id       uuid REFERENCES aav.devices(id),
  step            text NOT NULL,
  status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
  backup_verified boolean,
  backup_evidence jsonb,
  restore_outcome jsonb,
  return_to_service_approved_by uuid REFERENCES aav.users(id),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.coverage_records (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  layer        text NOT NULL,
  supported_assets jsonb NOT NULL DEFAULT '[]'::jsonb,
  available_signals jsonb NOT NULL DEFAULT '[]'::jsonb,
  gaps         jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, layer)
);

-- ---------------------------------------------------------------- settings / licensing / files
CREATE TABLE aav.settings (
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  category    text NOT NULL,
  key         text NOT NULL,
  value       jsonb NOT NULL,
  version     integer NOT NULL DEFAULT 1,
  updated_by  uuid REFERENCES aav.users(id),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, category, key)
);

CREATE TABLE aav.settings_history (
  id          bigserial PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  category    text NOT NULL,
  key         text NOT NULL,
  version     integer NOT NULL,
  value       jsonb,
  changed_by  uuid REFERENCES aav.users(id),
  changed_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE aav.subscriptions (
  tenant_id          uuid PRIMARY KEY REFERENCES aav.tenants(id) ON DELETE CASCADE,
  licence_unit       text NOT NULL DEFAULT 'per_user' CHECK (licence_unit IN ('per_user', 'per_device')),
  post_trial_policy  text NOT NULL DEFAULT 'paywall_console_keep_protection'
                     CHECK (post_trial_policy IN ('paywall_console_keep_protection', 'free_with_full_ads', 'lock_all')),
  trial_started_at   timestamptz NOT NULL DEFAULT now(),
  trial_days         integer NOT NULL DEFAULT 30 CHECK (trial_days = 30),
  price_pence        integer NOT NULL DEFAULT 499 CHECK (price_pence = 499),
  currency           text NOT NULL DEFAULT 'GBP' CHECK (currency = 'GBP'),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

-- One row per paid licence (a user or a device, per licence_unit). Rows are written only
-- from a verified payment-provider receipt; there is no admin "mark as paid" path.
CREATE TABLE aav.licences (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  holder_kind    text NOT NULL CHECK (holder_kind IN ('user', 'device')),
  holder_id      uuid NOT NULL,
  provider       text NOT NULL CHECK (provider IN ('google_play', 'app_store', 'web_checkout')),
  provider_ref   text NOT NULL,
  period_start   timestamptz NOT NULL,
  period_end     timestamptz NOT NULL CHECK (period_end > period_start),
  amount_minor   integer NOT NULL CHECK (amount_minor >= 0),   -- as reported by the store (local currency)
  currency       text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
  status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'refunded')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, provider_ref)
);

CREATE TABLE aav.vfs_nodes (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  parent_id    uuid REFERENCES aav.vfs_nodes(id) ON DELETE CASCADE,
  name         text NOT NULL CHECK (name !~ '[/\\\x00]' AND name NOT IN ('.', '..') AND length(name) BETWEEN 1 AND 255),
  kind         text NOT NULL CHECK (kind IN ('file', 'dir')),
  current_version integer,
  trashed_at   timestamptz,
  retain_until timestamptz,
  created_by   uuid REFERENCES aav.users(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX vfs_unique_live_name ON aav.vfs_nodes
  (tenant_id, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), name) WHERE trashed_at IS NULL;

CREATE TABLE aav.vfs_versions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  node_id     uuid NOT NULL REFERENCES aav.vfs_nodes(id) ON DELETE CASCADE,
  version     integer NOT NULL,
  sha256      text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes  bigint NOT NULL CHECK (size_bytes >= 0),
  mime        text NOT NULL,
  storage_key text NOT NULL,
  scan_status text NOT NULL CHECK (scan_status IN ('clean', 'infected', 'error')),
  scan_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by  uuid REFERENCES aav.users(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (node_id, version)
);

-- ---------------------------------------------------------------- audit (append-only, hash chained)
CREATE TABLE aav.audit_log (
  id         bigserial PRIMARY KEY,
  tenant_id  uuid REFERENCES aav.tenants(id) ON DELETE CASCADE,
  actor      text NOT NULL,
  action     text NOT NULL,
  target     text NOT NULL DEFAULT '',
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  trace_id   text,
  at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  prev_hash  text NOT NULL,
  hash       text NOT NULL
);

CREATE OR REPLACE FUNCTION aav.audit_chain() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public, aav AS $$
DECLARE prev text;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('aav.audit_log:' || COALESCE(NEW.tenant_id::text, 'global')));
  SELECT hash INTO prev FROM aav.audit_log
   WHERE tenant_id IS NOT DISTINCT FROM NEW.tenant_id ORDER BY id DESC LIMIT 1;
  NEW.prev_hash := COALESCE(prev, repeat('0', 64));
  NEW.hash := encode(digest(NEW.prev_hash || '|' || COALESCE(NEW.tenant_id::text, '') || '|' || NEW.actor || '|' ||
              NEW.action || '|' || NEW.target || '|' || NEW.detail::text || '|' ||
              to_char(NEW.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'), 'sha256'), 'hex');
  RETURN NEW;
END $$;
CREATE TRIGGER audit_chain BEFORE INSERT ON aav.audit_log FOR EACH ROW EXECUTE FUNCTION aav.audit_chain();

CREATE OR REPLACE FUNCTION aav.audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only'; END $$;
CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON aav.audit_log
  FOR EACH ROW EXECUTE FUNCTION aav.audit_immutable();

-- ---------------------------------------------------------------- RLS
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['memberships','policies','devices','enrollment_tokens','events','incidents','alerts',
    'quarantine_items','exclusions','scan_schedules','action_requests','approvals','commands','notifications',
    'investigations','integrations','external_alerts','protected_assets','service_objectives','traffic_policies',
    'recovery_items','coverage_records','settings','settings_history','subscriptions','licences','vfs_nodes',
    'vfs_versions']
  LOOP
    EXECUTE format('ALTER TABLE aav.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE aav.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON aav.%I USING (tenant_id = aav.current_tenant()) '
                   'WITH CHECK (tenant_id = aav.current_tenant())', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON aav.%I TO aav_app', t);
  END LOOP;
END $$;

-- Audit: tenant rows visible only in their tenant; global rows (tenant_id NULL) are
-- written by auth flows and readable only with no tenant context. Insert-only for the app.
ALTER TABLE aav.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE aav.audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_read ON aav.audit_log FOR SELECT
  USING (tenant_id IS NOT DISTINCT FROM aav.current_tenant());
CREATE POLICY audit_insert ON aav.audit_log FOR INSERT
  WITH CHECK (tenant_id IS NOT DISTINCT FROM aav.current_tenant());
GRANT SELECT, INSERT ON aav.audit_log TO aav_app;

-- Global identity tables: the app needs them for login before a tenant is chosen.
GRANT SELECT, INSERT, UPDATE ON aav.tenants, aav.users, aav.auth_tokens, aav.sessions, aav.outbound_mail TO aav_app;
GRANT DELETE ON aav.sessions TO aav_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA aav TO aav_app;

-- Membership lookup across tenants for the signed-in user only (needed to list a user's
-- tenants, e.g. an MSP operator). SECURITY DEFINER with a pinned search_path.
CREATE OR REPLACE FUNCTION aav.user_tenants(p_user uuid)
RETURNS TABLE (tenant_id uuid, tenant_name text, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT m.tenant_id, t.name, m.role FROM aav.memberships m JOIN aav.tenants t ON t.id = m.tenant_id
   WHERE m.user_id = p_user
$$;
REVOKE ALL ON FUNCTION aav.user_tenants(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.user_tenants(uuid) TO aav_app;

-- Device authentication happens before tenant context is known: resolve a device by its
-- key hash only. Returns no row for retired devices.
CREATE OR REPLACE FUNCTION aav.device_by_key(p_hash text)
RETURNS TABLE (device_id uuid, tenant_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT id, tenant_id FROM aav.devices WHERE device_key_hash = p_hash AND retired_at IS NULL
$$;
REVOKE ALL ON FUNCTION aav.device_by_key(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.device_by_key(text) TO aav_app;

-- Enrolment token lookup (pre-tenant). Consumes one use atomically.
CREATE OR REPLACE FUNCTION aav.consume_enrollment_token(p_hash text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
DECLARE tid uuid;
BEGIN
  UPDATE aav.enrollment_tokens SET uses = uses + 1
   WHERE token_hash = p_hash AND uses < max_uses AND expires_at > now()
  RETURNING tenant_id INTO tid;
  RETURN tid;
END $$;
REVOKE ALL ON FUNCTION aav.consume_enrollment_token(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.consume_enrollment_token(text) TO aav_app;

-- Integration lookup for inbound webhooks (pre-tenant): by id only.
CREATE OR REPLACE FUNCTION aav.integration_for_webhook(p_id uuid)
RETURNS TABLE (tenant_id uuid, webhook_secret_hash text, enabled boolean, maturity text, signal_kind text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT tenant_id, webhook_secret_hash, enabled, maturity, signal_kind FROM aav.integrations WHERE id = p_id
$$;
REVOKE ALL ON FUNCTION aav.integration_for_webhook(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.integration_for_webhook(uuid) TO aav_app;

-- Bootstrap: create a tenant with its first admin membership and subscription row. Used by
-- registration; runs as definer because no tenant context exists yet.
CREATE OR REPLACE FUNCTION aav.bootstrap_tenant(p_name text, p_user uuid, p_parent uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
DECLARE tid uuid;
BEGIN
  INSERT INTO aav.tenants (name, parent_msp_id) VALUES (p_name, p_parent) RETURNING id INTO tid;
  INSERT INTO aav.memberships (tenant_id, user_id, role) VALUES (tid, p_user, 'tenant_admin');
  INSERT INTO aav.subscriptions (tenant_id) VALUES (tid);
  RETURN tid;
END $$;
REVOKE ALL ON FUNCTION aav.bootstrap_tenant(text, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.bootstrap_tenant(text, uuid, uuid) TO aav_app;

-- Store-receipt handler (pre-tenant) resolves the tenant of a holder.
CREATE OR REPLACE FUNCTION aav.membership_exists(p_tenant uuid, p_user uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  SELECT EXISTS (SELECT 1 FROM aav.memberships WHERE tenant_id = p_tenant AND user_id = p_user)
$$;
REVOKE ALL ON FUNCTION aav.membership_exists(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.membership_exists(uuid, uuid) TO aav_app;
