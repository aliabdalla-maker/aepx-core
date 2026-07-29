-- Persists the Governance Engine's unconditional audit trail (Law 8) —
-- previously an in-memory list that was lost on every container restart.
CREATE SCHEMA IF NOT EXISTS governance;

CREATE TABLE IF NOT EXISTS governance.audit_log (
    id BIGSERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    event JSONB NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_recorded_at_idx ON governance.audit_log (recorded_at DESC);
