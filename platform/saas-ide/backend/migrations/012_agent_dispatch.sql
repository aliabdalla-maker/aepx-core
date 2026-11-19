-- Real AI agents: a platform-wide monthly AI spend cap and the two narrow functions the
-- isolated agent dispatcher needs. Apply as the migration role.
--
-- The monthly ledger holds no tenant data (one row per calendar month), so it is not RLS
-- scoped. Reservations move money from "reserved" to "spent" with the provider-reported cost;
-- a crash leaves the reservation held, which only ever under-spends the cap.
CREATE TABLE IF NOT EXISTS ide_ai_monthly_spend (
  month CHAR(7) PRIMARY KEY CHECK (month ~ '^[0-9]{4}-[0-9]{2}$'),
  reserved_microusd BIGINT NOT NULL DEFAULT 0 CHECK (reserved_microusd >= 0),
  spent_microusd BIGINT NOT NULL DEFAULT 0 CHECK (spent_microusd >= 0),
  runs INTEGER NOT NULL DEFAULT 0 CHECK (runs >= 0)
);

-- Per-run cost receipts from the provider (OpenRouter returns usage and cost on every
-- response). Tenant scoped, so a tenant can only ever read its own usage.
CREATE TABLE IF NOT EXISTS ide_ai_usage (
  id VARCHAR(36) PRIMARY KEY,
  tenant_id VARCHAR(128) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  run_id VARCHAR(36) NOT NULL,
  month CHAR(7) NOT NULL,
  provider VARCHAR(40) NOT NULL,
  model VARCHAR(120) NOT NULL DEFAULT '',
  provider_request_id VARCHAR(160),
  reserved_microusd BIGINT NOT NULL CHECK (reserved_microusd >= 0),
  actual_microusd BIGINT CHECK (actual_microusd >= 0),
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  state VARCHAR(16) NOT NULL DEFAULT 'reserved' CHECK (state IN ('reserved','settled','charged_max')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ide_ai_usage_tenant_day ON ide_ai_usage(tenant_id, created_at);
ALTER TABLE ide_ai_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE ide_ai_usage FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS ide_ai_usage_tenant ON ide_ai_usage;
CREATE POLICY ide_ai_usage_tenant ON ide_ai_usage
  USING (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''))
  WITH CHECK (tenant_id = NULLIF(current_setting('ide.tenant_id', true),''));

-- The dispatcher must find which tenants have approved work without reading any tenant's
-- rows: this returns tenant ids only, for queued jobs on approved runs.
CREATE OR REPLACE FUNCTION ide_dispatchable_tenants(p_limit INTEGER)
RETURNS TABLE(tenant_id VARCHAR)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT j.tenant_id FROM ide_agent_jobs j
  JOIN ide_agent_runs r ON r.id = j.run_id AND r.tenant_id = j.tenant_id
  WHERE j.state = 'pending' AND j.attempt < 2 AND j.next_attempt_at <= now()
    AND r.status IN ('approved','running')
  GROUP BY j.tenant_id
  ORDER BY min(j.created_at)
  LIMIT LEAST(GREATEST(p_limit, 1), 100);
$$;

-- reserve_budget() requires a tenant budget row; the runtime role may not insert budgets,
-- so this creates one at the platform ceiling. Real limits are the per-plan daily allowance
-- and the global monthly cap, both enforced by the metered worker before every provider call.
CREATE OR REPLACE FUNCTION ide_ensure_agent_budget(p_tenant VARCHAR, p_max_microusd BIGINT)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF p_tenant IS NULL OR length(p_tenant) NOT BETWEEN 1 AND 128
     OR p_max_microusd IS NULL OR p_max_microusd NOT BETWEEN 0 AND 1000000000 THEN
    RAISE EXCEPTION 'invalid agent budget' USING ERRCODE = '22023';
  END IF;
  INSERT INTO ide_agent_budgets (tenant_id, max_tokens, max_cost_microusd)
  VALUES (p_tenant, 1000000000, p_max_microusd)
  ON CONFLICT (tenant_id) DO UPDATE
    SET max_cost_microusd = GREATEST(ide_agent_budgets.max_cost_microusd, EXCLUDED.max_cost_microusd);
END;
$$;

REVOKE ALL ON FUNCTION ide_dispatchable_tenants(INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION ide_ensure_agent_budget(VARCHAR, BIGINT) FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ide_runtime') THEN
    GRANT EXECUTE ON FUNCTION ide_dispatchable_tenants(INTEGER) TO ide_runtime;
    GRANT EXECUTE ON FUNCTION ide_ensure_agent_budget(VARCHAR, BIGINT) TO ide_runtime;
    GRANT SELECT, INSERT, UPDATE ON ide_ai_monthly_spend, ide_ai_usage TO ide_runtime;
  END IF;
END $$;
