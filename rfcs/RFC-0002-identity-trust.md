# RFC-0002: Identity & Trust

Status: Draft
Author(s): AEP-X Founding Team
Created: 7 July 2026

## 1. Abstract

Defines the identity model and the 5-component trust formula every trust score in AEP-X is computed from.

## 2. Motivation

Law 2 (Trust Before Execution) requires a trust score to exist and mean the same thing everywhere it's checked — at the Gateway, inside Discovery's ranking function, and at the Connector Bus.

## 3. Design Goals

One trust formula, six trust levels, no per-service reinterpretation.

## 4. Specification

Trust Score = Identity(20%) + Behaviour(20%) + Security(20%) + Evidence(20%) + Reputation(20%), range 0–100.

Trust levels: 0–19 Untrusted, 20–39 Basic, 40–59 Verified, 60–79 Trusted, 80–94 Highly Trusted, 95–100 Certified.

Identity types: USER, AGENT, ORG, SERVICE, WORKFLOW, MODEL, DEVICE.

## 5. Data Model / Schema

`trust_scores` table, `schemas/sql/001_init.sql`.

## 6. Security & Compliance Considerations

OIDC/OAuth2/JWT/mTLS for authentication; RBAC/ABAC for authorization. This is also where AIA-R0–R4 assurance classification is assigned per-connector (SOA-Architecture.md §1.1) — a related but distinct scheme from the trust score above.

## 7. Backward Compatibility

The 5×20% weighting is the RFC-0002 normative formula (ADLC Plan §15.3 resolved this against an alternate 40/30/20/10 weighting found elsewhere in the source manual — RFC-0002 wins).

## 8. Reference Implementation

`services/identity/`, `services/trust/` (currently separate services in this scaffold — the existing Microservices-Implementation-Guide's "Trust Authority" merge is a later synthesis decision layered on top of this RFC, not a change to it; see Microservices-Implementation-Guide.html §1.1).

## 9. Open Questions

Whether Identity and Trust should be merged into one service (as the Microservices-Implementation-Guide does) or stay split (as this RFC and every Sprint 3.1–3.2 draft in the source manual do) — kept split here since re-merging would mean deleting working code for a distinction the source itself never defends either way.
