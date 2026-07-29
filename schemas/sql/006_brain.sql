-- The Brain service's self-learning state — persisted so learned
-- reliability patterns and circuit-breaker decisions survive a restart
-- (a "self-learning" system that forgets everything on every restart
-- isn't really learning).
CREATE SCHEMA IF NOT EXISTS brain;

CREATE TABLE IF NOT EXISTS brain.incidents (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN (
        'service_down', 'service_recovered', 'ollama_rewarmed',
        'circuit_opened', 'circuit_closed', 'circuit_half_open'
    )),
    target TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS brain_incidents_created_at_idx ON brain.incidents (created_at DESC);

CREATE TABLE IF NOT EXISTS brain.circuit_state (
    connector TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'closed' CHECK (state IN ('closed', 'open', 'half_open')),
    consecutive_failures INT NOT NULL DEFAULT 0,
    reliability_score NUMERIC NOT NULL DEFAULT 1.0,
    opened_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now()
);
