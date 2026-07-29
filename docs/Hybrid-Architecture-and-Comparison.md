# AEP-X — Hybrid Architecture & SOA-vs-Microservices Comparison

**Companion to:** [SOA-Architecture.md](SOA-Architecture.md), [Microservices-Architecture-v2.md](Microservices-Architecture-v2.md)
**Prepared:** 7 July 2026

---

## 1. The hybrid, in one diagram

```
                         Client · SDK · CLI · MCP
                                    │
                                    ▼
                              API Gateway
                                    │
                ┌───────────────────┴────────────────────┐
                ▼                                         ▼
    MICROSERVICES CORE (owned,                 SOA — AEP-X Connector Bus
    independently deployable,                  (mediates systems AEP-X
    choreographed via Kafka)                   does not own)
                │                                         │
    Tier 1: Registry, Trust,                  Coarse connector services:
    Discovery, Memory                         Enterprise, Industrial,
                │                              Productivity, Developer Tools,
    Tier 2: Workflow, Safety,                  AI Platform
    Governance, Knowledge,
    Cost Optimiser, ML                                    │
    Integration, Verification                             ▼
    (event-driven, own schemas)                External systems: SAP,
                │                              Salesforce, Workday, OPC-UA
                ▼                              plants, OpenAI, GitHub, Slack…
    Tier 3: PostgreSQL, Redis,
    Neo4j, Kafka, pgvector

    Both sides share: Trust Authority (trust check), Governance Engine (policy
    check + unconditional audit), the RFC-0001 message envelope, and Kafka as
    the event bus. Neither side re-implements these — that's what makes it one
    system with two integration styles, not two systems bolted together.
```

The boundary is not "SOA vs. microservices as competing choices for the whole platform" — it's **one platform, two integration styles applied where each fits**, sharing a governance and trust spine. This mirrors how real platforms with a similar shape (a core product plus a long tail of enterprise integrations) are actually built in practice — the debate in most real engineering organisations was settled this way years ago; AEP-X's source material just never named it.

## 2. Why the boundary sits exactly at "who owns the system"

Restated from [SOA-Architecture.md §2](SOA-Architecture.md#2-why-soa-fits-the-universal-connector-layer-and-not-the-core) as the single deciding question: **does AEP-X control the release cadence and protocol of the thing being integrated?**

- Registry, Trust, Memory, Workflow, Safety, Governance, Knowledge, Cost Optimiser, ML Integration, Verification — **yes**, AEP-X owns all of these. Independent deployability, database-per-service, and choreography pay off because each one changes on its own schedule and a bug in one shouldn't block releasing another.
- SAP, Salesforce, Workday, an OPC-UA-speaking factory PLC — **no**, AEP-X owns none of these. Independent deployability of "SAP connector" vs. "Salesforce connector" buys nothing, because neither changes because AEP-X wants it to; what's needed instead is one place that enforces trust/policy/audit consistently across all of them and translates their heterogeneous protocols into one canonical shape.

## 3. Comparison table

| Dimension | Microservices (core) | SOA / ESB (connector layer) |
|---|---|---|
| **Coupling** | Loose — services know only each other's APIs, own their schema | Loose to externals (adapter pattern hides their protocol), tighter internally (bus mediates every call) |
| **Deployment unit / cadence** | One service, deployed independently, as often as needed | One coarse connector service per category, deployed when that category's adapters change — usually far less often |
| **Scaling unit** | Per-service horizontal scaling (Discovery scales differently from Memory) | Per-category — an AI Platform Connector traffic spike scales that service, not Enterprise |
| **Protocol standardisation** | One internal standard (REST + Kafka, RFC-0001 envelope) | Many external protocols in, one canonical envelope out — the bus's entire job is this translation |
| **Governance enforcement point** | Distributed by convention (each service is expected to call Trust/Governance APIs) | Centralised, structurally enforced (every external call physically passes through the bus's trust/policy gate — Law 2 and Law 8 are harder to accidentally skip) |
| **Failure blast radius** | Contained to one service; Gateway surfaces a 503 (Microservices Guide §4.1) | Contained to one connector category; a SAP outage doesn't affect the AI Platform connector |
| **Cost/complexity to build N integrations** | High if used for external systems — N near-identical services, each re-implementing auth/retry/audit | Low — N adapters inside 5 coarse services sharing one mediation layer |
| **Fit for AEP-X's compliance model (AIA-R0–R4)** | Adequate for internal services, which don't carry per-external-system risk classification | Better — AIA-R classification is naturally a per-connector property, and the bus is the one place to enforce "no live traffic below the connector's required assurance tier" |
| **Evolvability** | Change one service without touching others (Law 10, Evolution) | Change one adapter without touching the bus or other adapters |
| **Anti-pattern risk if misapplied** | "Distributed monolith" if services share a database (Microservices Guide §4.3 already guards against this) | "God bus" if the bus grows business logic beyond mediation (§3.1 rule 5 in SOA-Architecture.md guards against this) |

## 4. What NOT to build — staying inside the "extremely low cost" positioning

The ADLC Plan's Critical Evaluation (§15.2.1, "over-engineering") and the Instructional Manual's own MVP discipline ("Do NOT use: Kubernetes / Kafka / Neo4j / NATS / multi-region deployment, yet") both apply here with equal force:

- **Do not adopt a commercial ESB product** (MuleSoft, BizTalk, IBM App Connect). The AEP-X Connector Bus is a ~200-line FastAPI mediation service plus the Kafka bus the core already runs. A commercial ESB is exactly the "extremely low cost, vendor neutral" positioning's opposite.
- **Do not build all 25+ named external systems before validating the pattern on one per category.** SOA-Architecture.md §5's build sequence deliberately does Salesforce-only, GitHub-only, Slack-only, OpenAI-only first.
- **Do not let the SOA layer duplicate governance logic.** It calls the existing Trust Authority and Governance Engine APIs — it does not grow its own trust-scoring or policy-evaluation code. If it ever does, that's a sign the "shared spine" in §1 has been broken.
- **Do not re-open Marketplace Engine, Government/Education connectors, or Industrial connectors** to justify building the SOA layer — none of that deferral is affected by this document; see the cross-walk in SOA-Architecture.md §1.2.

## 5. Recommendation

Build both, on the schedule already implied by the two companion documents: finish the Microservices v2 additions (Knowledge Service, Verification Engine, Cost Optimiser, ML Integration — these unlock the platform's core economic and anti-hallucination claims) before starting the SOA Connector Bus (Weeks 13+, gated on Trust Authority + Governance Engine being healthy in production, exactly as Marketplace Engine was gated). The two are not in tension for engineering capacity — the SOA layer's first cut is a thin mediation service reusing the core's existing trust/policy/audit APIs, not a second platform to design from scratch.

---

*AEP-X — Hybrid Architecture & Comparison · Companion to SOA-Architecture.md and Microservices-Architecture-v2.md · 7 July 2026*
