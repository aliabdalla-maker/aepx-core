-- Additive migration on top of schemas/sql/001_init.sql (Instructional
-- Manual §2.1). Each service owns its own schema — see Microservices Guide
-- §4.3, database-per-service enforced via roles.

CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector, for knowledge.embeddings

CREATE TABLE IF NOT EXISTS knowledge.entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence NUMERIC DEFAULT 0.8,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE SCHEMA IF NOT EXISTS verification;

CREATE TABLE IF NOT EXISTS verification.results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL,
    claim_count INT NOT NULL,
    truth_score NUMERIC NOT NULL,
    confidence_band TEXT NOT NULL CHECK (confidence_band IN ('GREEN', 'AMBER', 'RED', 'GREY')),
    citations JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE SCHEMA IF NOT EXISTS ml;

CREATE TABLE IF NOT EXISTS ml.models (
    name TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    trained_at TIMESTAMPTZ,
    sample_count INT DEFAULT 0
);

-- Roles, per Microservices Guide §4.3 — never grant cross-schema access.
-- CREATE ROLE knowledge_svc LOGIN PASSWORD '...';
-- GRANT ALL ON SCHEMA knowledge TO knowledge_svc;
-- CREATE ROLE verification_svc LOGIN PASSWORD '...';
-- GRANT ALL ON SCHEMA verification TO verification_svc;
-- CREATE ROLE ml_svc LOGIN PASSWORD '...';
-- GRANT ALL ON SCHEMA ml TO ml_svc;
