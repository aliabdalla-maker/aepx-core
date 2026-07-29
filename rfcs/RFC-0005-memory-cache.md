# RFC-0005: Memory & Cache

Status: Draft
Author(s): AEP-X Founding Team
Created: 7 July 2026

## 1. Abstract

Defines the canonical M0–M6 memory layers and L0–L5 cache layers — normative per ADLC Plan §15.3, reaffirmed after reading the full source manual end-to-end (SOA-Architecture.md §1.1).

## 2. Motivation

The source manual contains at least half a dozen conflicting versions of these layer counts and names across its ~30 drafting passes. One normative version has to win, or every service that touches memory or cache reimplements its own interpretation.

## 3. Design Goals

Cache-first economics (Law 5): never invoke an LLM if cache/memory/knowledge already has the answer.

## 4. Specification

**Memory:** M0 Prompt (single request) → M1 Session (hours) → M2 Episodic (days–years) → M3 Semantic (long-term) → M4 Procedural → M5 Organisational → M6 Federated.

**Cache:** L0 Prompt (5 min) → L1 Session (1 h) → L2 Agent (24 h) → L3 Workflow (7 d) → L4 Organisation (30 d) → L5 Federation (policy-controlled — Governance Engine decides per call).

Cost optimisation rules: cache first, memory before retrieval, retrieval before generation, smallest sufficient model, reuse before recompute.

## 5. Data Model / Schema

`memory_entries` table (`schemas/sql/001_init.sql`); cache is Redis-only, keyed `{layer}:{key}`.

## 6. Security & Compliance Considerations

L5 (Federation) cache writes require an explicit Governance Engine policy check before storage — the only cache layer that isn't a pure TTL-based store.

## 7. Backward Compatibility

Supersedes the Instructional Manual §3.5 reduced-scope MVP (`L1 Session Cache, TTL = 1 hour` only) — that was an explicit, temporary scope reduction, not a competing spec.

## 8. Reference Implementation

`services/memory/`, `services/cache/`, `services/knowledge/`.

## 9. Open Questions

None — this is the one layer model where the full-document read (SOA-Architecture.md §1.1) confirmed rather than contradicted the existing ADLC Plan resolution.
