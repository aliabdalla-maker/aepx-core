"""Durable MCP remote intent ledger schema. Apply only in isolated migrations.

Runtime must use a non-owner, non-BYPASSRLS PostgreSQL role and set
transaction-local app.tenant_id from verified authorization context.
"""
DDL = """
CREATE TABLE IF NOT EXISTS mcp_remote_execution_intents (
    tenant_id uuid NOT NULL,
    request_id uuid NOT NULL,
    approval_id uuid NOT NULL,
    action_hash char(64) NOT NULL CHECK (action_hash ~ '^[0-9a-f]{64}$'),
    resource_id text NOT NULL CHECK (resource_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$'),
    tool_name text NOT NULL CHECK (tool_name ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$'),
    protocol_version text NOT NULL CHECK (protocol_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$'),
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
