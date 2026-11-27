-- Release 2: agent memory with access-controlled retrieval (AGT-03, AGT-04) and business KPIs (KPI-01).

-- Memory items are tenant-scoped (RLS), versioned (key + version; older versions are superseded, never edited),
-- provenance-tracked (source_kind/source_ref/created_by), consent-aware (personal data needs a consent basis) and
-- retention-bound (retain_until; aav.apply_memory_retention deletes expired items). Retrieval is PostgreSQL full-text
-- search: no extra service, fits Always Free, and the access check (required_permission) is applied in the query.
CREATE TABLE aav.memory_items (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              uuid NOT NULL REFERENCES aav.tenants(id) ON DELETE CASCADE,
  key                    uuid NOT NULL,
  version                integer NOT NULL CHECK (version >= 1),
  kind                   text NOT NULL CHECK (kind IN ('incident_note', 'runbook', 'finding', 'decision', 'reference')),
  title                  text NOT NULL CHECK (length(title) BETWEEN 1 AND 300),
  content                text NOT NULL CHECK (length(content) BETWEEN 1 AND 20000),
  source_kind            text NOT NULL CHECK (source_kind IN ('incident', 'alert', 'investigation', 'file', 'user', 'external')),
  source_ref             text NOT NULL DEFAULT '',
  required_permission    text NOT NULL DEFAULT 'incidents.read',
  contains_personal_data boolean NOT NULL DEFAULT false,
  consent_basis          text,
  retain_until           timestamptz,
  created_by             text NOT NULL,
  created_at             timestamptz NOT NULL DEFAULT now(),
  superseded_at          timestamptz,
  tsv                    tsvector GENERATED ALWAYS AS (to_tsvector('simple', title || ' ' || content)) STORED,
  UNIQUE (tenant_id, key, version),
  CHECK (NOT contains_personal_data OR consent_basis IS NOT NULL)
);
CREATE INDEX memory_items_tsv ON aav.memory_items USING gin (tsv);
CREATE INDEX memory_items_current ON aav.memory_items (tenant_id, key) WHERE superseded_at IS NULL;
ALTER TABLE aav.memory_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE aav.memory_items FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON aav.memory_items USING (tenant_id = aav.current_tenant())
  WITH CHECK (tenant_id = aav.current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON aav.memory_items TO aav_app;

CREATE OR REPLACE FUNCTION aav.apply_memory_retention()
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
DECLARE n bigint;
BEGIN
  DELETE FROM aav.memory_items WHERE retain_until IS NOT NULL AND retain_until < now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;
REVOKE ALL ON FUNCTION aav.apply_memory_retention() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.apply_memory_retention() TO aav_app;

-- KPI-01 business KPIs across tenants, aggregated only (no tenant names, ids or user identities leave the function).
CREATE OR REPLACE FUNCTION aav.business_kpis()
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, aav AS $$
  WITH t AS (SELECT id, created_at FROM aav.tenants),
  s AS (SELECT user_id, created_at FROM aav.sessions),
  act AS (SELECT t.id, EXISTS (SELECT 1 FROM aav.devices d WHERE d.tenant_id = t.id) AS activated,
                 EXISTS (SELECT 1 FROM aav.licences l WHERE l.tenant_id = t.id AND l.status = 'active'
                         AND l.period_end > now()) AS paying,
                 EXISTS (SELECT 1 FROM aav.subscriptions sub WHERE sub.tenant_id = t.id
                         AND sub.trial_started_at + make_interval(days => sub.trial_days) < now()) AS trial_ended
          FROM t),
  prev AS (SELECT DISTINCT user_id FROM s WHERE created_at BETWEEN now() - interval '60 days' AND now() - interval '30 days'),
  cur AS (SELECT DISTINCT user_id FROM s WHERE created_at > now() - interval '30 days'),
  feat(name, n) AS (
    SELECT 'endpoint_protection', count(DISTINCT tenant_id) FROM aav.devices
    UNION ALL SELECT 'scheduled_scans', count(DISTINCT tenant_id) FROM aav.scan_schedules
    UNION ALL SELECT 'response_actions', count(DISTINCT tenant_id) FROM aav.action_requests
    UNION ALL SELECT 'investigations', count(DISTINCT tenant_id) FROM aav.investigations
    UNION ALL SELECT 'integrations', count(DISTINCT tenant_id) FROM aav.integrations
    UNION ALL SELECT 'files', count(DISTINCT tenant_id) FROM aav.vfs_nodes
    UNION ALL SELECT 'memory', count(DISTINCT tenant_id) FROM aav.memory_items)
  SELECT jsonb_build_object(
    'tenants', (SELECT count(*) FROM t),
    'new_tenants_30d', (SELECT count(*) FROM t WHERE created_at > now() - interval '30 days'),
    'active_users_7d', (SELECT count(DISTINCT user_id) FROM s WHERE created_at > now() - interval '7 days'),
    'active_users_30d', (SELECT count(*) FROM cur),
    'activation_rate', (SELECT round(avg(CASE WHEN activated THEN 1.0 ELSE 0.0 END), 4) FROM act),
    'conversion_rate', (SELECT round(avg(CASE WHEN paying THEN 1.0 ELSE 0.0 END), 4) FROM act WHERE trial_ended),
    'paying_tenants', (SELECT count(*) FROM act WHERE paying),
    'retention_30d', (SELECT CASE WHEN count(*) = 0 THEN NULL
                                  ELSE round(count(*) FILTER (WHERE user_id IN (SELECT user_id FROM cur))::numeric / count(*), 4) END
                      FROM prev),
    'feature_adoption', (SELECT jsonb_object_agg(name, CASE WHEN (SELECT count(*) FROM t) = 0 THEN 0
                                                            ELSE round(n::numeric / (SELECT count(*) FROM t), 4) END) FROM feat),
    'computed_at', now())
$$;
REVOKE ALL ON FUNCTION aav.business_kpis() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION aav.business_kpis() TO aav_app;
