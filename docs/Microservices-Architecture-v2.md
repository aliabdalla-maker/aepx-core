# AEP-X — Microservices Architecture v2 Addendum

**Source:** `AEP-X Ultra (1).docx` (see [SOA-Architecture.md §1](SOA-Architecture.md) for the full reconciliation of this source)
**Extends:** Microservices-Implementation-Guide.html (the 7-service Tier 1/Tier 2 architecture already built)
**Prepared:** 7 July 2026

---

## 1. Reconciliation — what this addendum adds and why it's separate from the original guide

The original Microservices-Implementation-Guide reconciled a short "Volume 9" service-catalogue outline into 7 buildable services (Agent Registry, Trust Authority, Discovery, Memory, Workflow Engine, Safety Engine, Governance Engine) plus a backlogged Marketplace Engine. This new source, read in full, adds four engine families that outline never named at build-detail level:

| New engine family | Where it comes from in the source | Already partially covered? |
|---|---|---|
| **Knowledge Service** | Sprint 2.3 Knowledge Service MVP; RFC-0005 §"Knowledge"; distinct from Memory Service throughout every pass | No — Memory Service (Instructional Manual §3.5) only covers session memory; semantic/knowledge retrieval was always a separate service in every sprint draft |
| **ML Integration Layer** (Prediction Engine, Learning Engine, Optimisation Engine) | "Machine Learning Integration Layer" (early pass): Classification / Prediction / Recommendation / Continuous Learning | No — ADLC Plan §12 mentions "the ML fabric (classification, prediction, recommendation)" only as a Phase G/H operations concept, never designed as a service |
| **Anti-Hallucination Engine V2 / Verification Engine** | Distinct from Safety Engine in the source: Safety Engine (RFC-0007) does risk classification and escalation; **Verification Engine** (Sprint 4.3) does claim extraction → evidence correlation → truth scoring → confidence → citation, as five named sub-engines | Partially — Instructional Manual §4.4 built an "anti-hallucination validation stub" but conflated it with Safety Engine's response contract; this addendum treats Verification as its own service, consuming Safety Engine's classification as an input |
| **Universal Cost Optimiser** | "Universal Cost Optimiser" (early pass) and Cost Engine/Utility Engine (RFC-0008) — Utility Score = Accuracy + Trust + Compliance + Performance − Cost − Latency − Energy − Risk | No — cache-first routing exists as a *principle* (RFC-0008 invariants, already in ADLC Plan §2) but no service computes and applies the Utility Score at request time |

**Scope discipline check.** This is new Tier 2 (event-driven) surface, same tier as Workflow/Safety/Governance. Per the same discipline the original guide applied to Marketplace Engine: **build order matters more than completeness**. The four services below are ordered by dependency and by how directly they serve the platform's core economic claim (cache-first, 80% LLM-cost reduction — ADLC Plan §9) rather than by how the source happens to list them.

---

## 2. Updated architecture overview

The original three tiers are unchanged. This addendum extends **Tier 2 only**:

- **Tier 1 — Foundational (synchronous, unchanged):** Agent Registry, Trust Authority, Discovery Service, Memory Service.
- **Tier 2 — Orchestration (event-driven), extended:** Workflow Engine, Safety Engine, Governance Engine, Marketplace Engine (backlog) **+ Knowledge Service, Cost Optimiser Service, ML Integration Service, Verification Engine (new)**.
- **Tier 3 — Infrastructure, extended:** PostgreSQL, Redis, Neo4j, Kafka **+ pgvector on the existing PostgreSQL instance** (Knowledge Service needs vector similarity search; this is an extension in-place, not a new data store).

The dependency-ordering rule from the original guide holds: **no Tier 2 service calls another Tier 2 service synchronously.** The four new services follow it exactly as Workflow/Safety/Governance do — they read Tier 1 services via API and communicate with each other only by publishing/consuming Kafka events.

---

## 3. Service catalogue additions

| Service | Owns (bounded context) | Exposes | Depends on | Data store |
|---|---|---|---|---|
| **Knowledge Service** | Validated facts, source documents, knowledge embeddings | `POST/GET /knowledge`, `POST /knowledge/search` | Memory Service (read, for context); Neo4j (graph relationships) | PostgreSQL + pgvector (`knowledge.*`) |
| **Verification Engine** (Anti-Hallucination V2) | Evidence correlation records, truth/confidence scores, citations | `POST /verify` | Knowledge Service (read); consumes `workflow.completed` | PostgreSQL (`verification.*`); publishes `verification.completed` to Kafka |
| **Cost Optimiser Service** | Utility Score computations, routing decisions | `POST /route/decide` | Trust Authority, Safety Engine (read, for the Trust/Compliance/Risk terms) | Redis (routing-decision cache only — no system of record; every decision is a pure function of current inputs) |
| **ML Integration Service** | Prediction/recommendation models, learning-loop state | `POST /predict`, `POST /recommend` | Consumes `workflow.completed`, `safety.flagged`, `verification.completed` (the feedback loop, Law 9) | PostgreSQL (`ml.*`) for model registry/metadata; model artifacts in object storage (MinIO) |

**The one rule that still applies:** every row owns its own schema. Cost Optimiser Service in particular is tempting to let read Trust Authority's `trust_scores` table directly since it needs that number on every request — don't. Call the API. The <5 ms cache-lookup budget (ADLC Plan §9) is met by caching the *Trust Authority response*, not by bypassing the service boundary.

---

## 4. Communication patterns — additions

### 4.1 Cost Optimiser sits in the synchronous path, as an exception to Tier 2's async-only rule

Every other Tier 2 service is async-only (§4.2 of the original guide). Cost Optimiser Service is the one deliberate exception: routing decisions must be available **before** an LLM call is made, not after, so `POST /route/decide` is a synchronous call from the Gateway, budgeted at <20 ms (tighter than the general Tier-1 100 ms budget, because it sits on the hot path of every request that might otherwise hit an LLM). Justify this exception explicitly in the PR — it is the only synchronous Tier 2 call in the system, and it must stay that way; if a second one gets proposed later, that's a signal the tier boundary needs re-examining, not a precedent to repeat casually.

### 4.2 The extended event flow

```
Workflow Engine  ──publishes──▶ workflow.completed
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
             Safety Engine    Governance Engine   Verification Engine
             (existing)       (existing, audits    (NEW — extracts claims,
                               unconditionally)      correlates evidence,
                    │                                 computes truth score)
                    │                                      │
                    ▼                                      ▼
            safety.flagged (existing)          verification.completed (NEW)
                    │                                      │
                    └──────────────┬───────────────────────┘
                                   ▼
                         ML Integration Service (NEW)
                         — consumes both, updates prediction/
                           recommendation models (Law 9 learning loop)
                                   │
                                   ▼
                         trust.updated (existing topic, now also
                         fed by ML Integration Service's outcomes,
                         not only Trust Authority's own logic)
```

Knowledge Service does not sit in this event chain — it is called synchronously (Tier 1 style, even though it's cataloged as Tier 2 for governance/audit purposes) by Workflow Engine and Verification Engine whenever a step needs a fact looked up or a claim checked against a validated source.

### 4.3 Cache/memory layer implementation, now canonical

Instructional Manual §3.5 built only `L1 Session Cache, TTL = 1 hour` — an explicit reduced-scope MVP choice ("Do not build L2–L5 yet", per that document's own text). This addendum extends the Cache Service to the full canonical model resolved in ADLC Plan §15.3 and pinned to concrete TTLs by this source's Sprint 2.2 MVP spec:

| Layer | Scope | TTL |
|---|---|---|
| L0 Prompt Cache | Exact-match prompt+context hash | 5 minutes |
| L1 Session Cache | Per-session, already built | 1 hour |
| L2 Agent Cache | Per-agent, cross-session | 24 hours |
| L3 Workflow Cache | Per-workflow-definition result reuse | 7 days |
| L4 Organisation Cache | Cross-agent, per-organisation | 30 days |
| L5 Federation Cache | Cross-organisation | Policy-controlled (Governance Engine decides, per call, whether federation-tier reuse is permitted for the requesting org) |

```python
# services/cache/app/main.py — extends the existing Instructional Manual §3.5 stub
CACHE_LAYERS = {
    "L0": 300,      # 5 minutes
    "L1": 3600,     # 1 hour — already built
    "L2": 86400,    # 24 hours
    "L3": 604800,   # 7 days
    "L4": 2592000,  # 30 days
    # L5 has no fixed TTL — Governance Engine policy decides per call
}

@app.get("/cache/{layer}/{key}")
def get_cache(layer: str, key: str):
    val = r.get(f"{layer}:{key}")
    return {"layer": layer, "key": key, "value": json.loads(val) if val else None, "hit": val is not None}

@app.post("/cache/{layer}/{key}")
def set_cache(layer: str, key: str, value: dict):
    if layer not in CACHE_LAYERS:
        raise HTTPException(400, f"unknown layer {layer}")
    r.set(f"{layer}:{key}", json.dumps(value), ex=CACHE_LAYERS[layer])
    return {"stored": True, "layer": layer, "ttl": CACHE_LAYERS[layer]}
```

Cost Optimiser Service's routing decision (§4.1) is what decides *which* layer to check first and how far down the L0→L5→Memory→Knowledge→Model hierarchy to fall through — the Cache Service itself stays a dumb key-value store per layer, exactly as designed.

---

## 5. Event contracts — additions

| Topic | Producer | Consumers | Payload shape |
|---|---|---|---|
| `verification.completed` | Verification Engine | Governance Engine (audit), ML Integration Service (learning input) | `{workflow_id, claim_count, truth_score, confidence_band, citations[]}` |
| `ml.prediction.made` | ML Integration Service | Cost Optimiser Service (optional — informs future routing) | `{prediction_type, target_id, value, confidence, model_version}` |
| `knowledge.updated` | Knowledge Service | Verification Engine (cache invalidation — a claim verified against stale knowledge should be re-checked) | `{knowledge_id, source, updated_fields[], ts}` |

These follow the original guide's rule: name topics when the producer exists, don't pre-build consumers for events nothing produces yet.

---

## 6. Confidence bands — Verification Engine implementation

Reuses the exact band structure the source repeats consistently across every pass (this is one of the few things that *didn't* drift between drafts):

```python
# services/verification/app/main.py
CONFIDENCE_BANDS = [(95, "GREEN"), (80, "AMBER"), (60, "RED"), (0, "GREY")]
# GREEN=Verified, AMBER=Inference, RED=Challenge, GREY=Risk (source's own labels)

def band_for(truth_score: float) -> str:
    for threshold, label in CONFIDENCE_BANDS:
        if truth_score >= threshold:
            return label
    return "GREY"
```

This produces the same `{answer, confidence, evidence[], verification_status}` contract Safety Engine already returns (Instructional Manual §4.4) — Verification Engine is a deeper pipeline feeding that same contract with a real truth score instead of the Alpha-stage placeholder (`len(evidence) * 0.35`), not a competing contract.

---

## 7. Definition of Done — Microservices v2 milestone

- Knowledge Service, Verification Engine, Cost Optimiser Service, and ML Integration Service all report `"status": "ok"` on `/health` through the Gateway.
- Cache Service serves all six layers (L0–L5) with the TTLs in §4.3; a request that misses L0 through L4 and is denied at L5 by Governance Engine policy returns a clear `{"cache_hit": false, "reason": "L5_policy_denied"}`, not a silent fallback.
- `POST /route/decide` responds in <20 ms p95 and its decision is logged with the full Utility Score breakdown (Accuracy/Trust/Compliance/Performance − Cost/Latency/Energy/Risk) so a routing decision can be explained after the fact (Law 7, Explainability).
- A workflow completion produces a `verification.completed` event with a real truth score (not the Alpha placeholder), and ML Integration Service's learning-loop consumption of it is visible in its model-metadata table within 1 second.
- This milestone is recorded in `governance/decisions/`, noting explicitly that Marketplace Engine, Government/Education connectors, and Industrial connectors remain backlog.

---

*AEP-X — Microservices Architecture v2 Addendum · Companion to ADLC-Plan, Handoff, Instructional-Manual, and Microservices-Implementation-Guide · 7 July 2026*
