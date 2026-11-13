"""Offline durable remote intent ledger schema (PostgreSQL).

No migration is applied automatically. Dispatchers MUST reserve before network I/O,
use the same provider idempotency key, and reconcile unknown outcomes instead of
blindly retrying. RLS requires a transaction-local app.tenant_id setting.
"""
DDL = """
CREATE TABLE IF NOT EXISTS mcp_remote_execution_intents (
    tenant_id uuid NOT NULL,
    request_id uuid NOT NULL,
    approval_id uuid NOT NULL,
    action_hash char(64) NOT NULL CHECK (action_hash ~ '^[0-9a-f]{64}$'),
    resource_id text NOT NULL CHECK (length(resource_id) BETWEEN 1 AND 256),
    tool_name text NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    protocol_version text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    state text NOT NULL DEFAULT 'reserved'
      CHECK (state IN ('reserved', 'dispatched', 'uncertain', 'succeeded', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, request_id),
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, approval_id, action_hash)
);
ALTER TABLE mcp_remote_execution_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_remote_execution_intents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mcp_remote_intent_tenant ON mcp_remote_execution_intents;
CREATE POLICY mcp_remote_intent_tenant ON mcp_remote_execution_intents
USING (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);
"""
