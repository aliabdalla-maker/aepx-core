-- RFC-0006: blockchain ecosystem — a new connector category, tamper-evident
-- audit anchoring, and decentralized identity (did:key).

-- 1. Widen the connector category CHECK to admit 'blockchain' (found
--    dynamically rather than hardcoding Postgres's auto-generated
--    constraint name, since that name was never pinned in 003_connectors.sql).
DO $$
DECLARE
    con_name TEXT;
BEGIN
    SELECT conname INTO con_name
    FROM pg_constraint
    WHERE conrelid = 'connectors.registry'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%category%';
    IF con_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE connectors.registry DROP CONSTRAINT %I', con_name);
    END IF;
END $$;

ALTER TABLE connectors.registry ADD CONSTRAINT registry_category_check
    CHECK (category IN ('enterprise', 'productivity', 'devtools', 'aiplatform', 'data', 'messaging', 'industrial', 'cloud', 'government', 'education', 'blockchain'));

INSERT INTO connectors.registry (name, category, protocols, ai_risk_class, min_trust_score, maturity) VALUES
    ('ethereum', 'blockchain', 'JSON-RPC', 'AIA-R2', 60, 'specialized'),
    ('polygon', 'blockchain', 'JSON-RPC', 'AIA-R2', 60, 'stub'),
    ('base', 'blockchain', 'JSON-RPC', 'AIA-R2', 60, 'stub'),
    ('avalanche', 'blockchain', 'JSON-RPC', 'AIA-R2', 60, 'stub'),
    ('bitcoin', 'blockchain', 'JSON-RPC', 'AIA-R2', 60, 'stub'),
    ('solana', 'blockchain', 'JSON-RPC', 'AIA-R2', 60, 'stub'),
    ('hyperledger-fabric', 'blockchain', 'gRPC', 'AIA-R1', 50, 'stub')
ON CONFLICT (name) DO NOTHING;

-- 2. Governance's tamper-evident audit anchoring (services/governance/app/ledger.py) —
--    a local SHA-256 hash chain over batches of governance.audit_log, optionally
--    also anchored on an EVM chain (governance/contracts/AEPXAnchor.sol).
CREATE TABLE IF NOT EXISTS governance.ledger_anchors (
    id BIGSERIAL PRIMARY KEY,
    seq_no BIGINT UNIQUE NOT NULL,
    prev_hash TEXT,
    merkle_root TEXT NOT NULL,
    anchor_hash TEXT NOT NULL,
    entry_count INT NOT NULL,
    first_audit_id BIGINT NOT NULL,
    last_audit_id BIGINT NOT NULL,
    backend TEXT NOT NULL DEFAULT 'local-hashchain',
    tx_ref TEXT,
    anchored_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ledger_anchors_last_audit_id_idx ON governance.ledger_anchors (last_audit_id);

-- 3. Decentralized identity — did:key (services/identity/app/did.py), stored
--    against the owning agent. Nullable: existing rows are unaffected, and
--    an agent registered while Identity is unreachable simply has none yet.
ALTER TABLE agents ADD COLUMN IF NOT EXISTS did TEXT UNIQUE;
