-- Minimum schema for the 6 in-scope Instructional-Manual services.
-- Per Instructional Manual §2.1: extend later, don't front-load fields
-- you don't need yet.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '0.0.1',
    trust_score INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    version TEXT NOT NULL
);

CREATE TABLE agent_capabilities (
    agent_id UUID REFERENCES agents(id),
    capability_id UUID REFERENCES capabilities(id),
    confidence NUMERIC DEFAULT 0.8,
    cost NUMERIC DEFAULT 0,
    latency_ms INT DEFAULT 0,
    PRIMARY KEY (agent_id, capability_id)
);

CREATE TABLE trust_scores (
    entity_id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL,
    identity_score INT DEFAULT 0,
    behaviour_score INT DEFAULT 0,
    security_score INT DEFAULT 0,
    evidence_score INT DEFAULT 0,
    reputation_score INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE memory_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id),
    layer TEXT NOT NULL CHECK (layer IN ('M1_SESSION','M2_EPISODIC','M3_SEMANTIC')),
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);
