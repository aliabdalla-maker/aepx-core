# RFC-0004: Discovery & Federation

Status: Draft
Author(s): AEP-X Founding Team
Created: 7 July 2026

## 1. Abstract

Defines capability-based agent discovery and its ranking function.

## 2. Motivation

Given a capability, an agent or workflow needs a well-defined way to find the best available provider — not just any provider.

## 3. Design Goals

Fast (<50ms uncached, <10ms cached), trust-aware, cost-aware ranking.

## 4. Specification

Ranking score = 40% capability match + 25% trust + 15% availability − 10% latency − 10% cost (Microservices-Implementation-Guide.html §5.1). Federation levels F0 (Local) through F5 (Global) are named in the source manual but out of scope until post-GA (ADLC Plan §6.1).

## 5. Data Model / Schema

Stateless — reads Registry and Trust via API, caches ranked results in Redis only.

## 6. Security & Compliance Considerations

Discovery never writes to another service's tables; ranking inputs come only from public API responses.

## 7. Backward Compatibility

Ranking weights may be tuned with pilot data (ADLC Plan §15.4 flags the current weights as provisional, not a platform guarantee).

## 8. Reference Implementation

`services/discovery/`.

## 9. Open Questions

Federation levels F1+ — deferred to post-GA per ADLC Plan §6.1.
