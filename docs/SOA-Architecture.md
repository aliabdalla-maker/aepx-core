# AEP-X — SOA Architecture Implementation Guide

**Source:** `AEP-X Ultra (1).docx` — a 36,937-paragraph consolidated draft (~30 successive re-planning passes, Version 2.0 through Version ∞, plus a business/governance chain and a return to concrete sprint execution). Full copy retained at [`../attachment/AEP-X Ultra v2 (source).docx`](../attachment/AEP-X%20Ultra%20v2%20%28source%29.docx).
**Companion to:** ADLC-Plan, Handoff, Instructional-Manual, Microservices-Implementation-Guide
**Prepared:** 7 July 2026

---

## 1. Reconciliation — how this source relates to the existing plan

**What this document is.** Unlike the prior "Volume 9" outline source, this attachment is the full escalating draft chain itself — Executive Vision → PESTEL → SPARC-Native Lifecycle → Universal Plug and Connect Framework → "V3 Standards Programme" (RFC roadmap) → nine further "Stage"/"Programme" re-plannings that climb to increasingly aspirational scope (Autonomous Intelligence Internet, Agent Operating System, Planetary Intelligence Grid, "AEP-X Zero — Version ∞") → a ~10,000-line business/governance chain (PMO, HR, BCP, ESG, ISO roadmap, M&A, IPO/Exit, 20-year Legacy Framework) → a return to concrete Sprint 0–4 build specs and RFC-0001–0010 / RA-0001–0008 full text. It is the "3,188-page consolidated edition" the ADLC Plan's Critical Evaluation (§15.2.8) already warned about: ~30 restart points, each ending "the next step is…", with terminology drifting between passes.

**Why an SOA document at all.** The source never once uses the words "SOA," "service-oriented," or "ESB" — that framing is this engagement's, not the manual's. But the source *does* independently converge, over and over, on a `Connector Contract` that names the exact protocol mix classic SOA/ESB architectures exist to mediate: `Supports: MCP, REST, GraphQL, gRPC, MQTT, Kafka, NATS, SOAP, OPC-UA, Custom`, plus a generic `Connector` interface (`authenticate / discover / execute / monitor`) and a `ProtocolAdapter` interface (`connect / execute / disconnect`). The **Universal Connector Layer (UCL)** — Enterprise (SAP, Salesforce, MS Dynamics, Oracle, Workday, ServiceNow), Industrial (SCADA, PLC, OPC-UA, Modbus, BACnet), Productivity (Google Workspace, M365, Slack, Teams, Zoom), Developer (GitHub, GitLab, Jira, Confluence, Azure DevOps), AI Platforms (OpenAI, Anthropic, Gemini, Mistral, Ollama, vLLM, HuggingFace), Government/Education — is the one part of this source that is *not* well served by the microservices style already committed in the Microservices-Implementation-Guide. This document designs that layer as SOA, and leaves the AI-native core (Registry, Trust, Memory, Workflow, Safety, Governance) as microservices, exactly as already built. See [Hybrid-Architecture-and-Comparison.md](Hybrid-Architecture-and-Comparison.md) for why the boundary sits there.

### 1.1 Contradictions in this source — inherited, not re-litigated

The ADLC Plan (§15.3) already resolved the memory/cache layer and RFC-numbering contradictions found in the original manual. Reading this new, much larger attachment end-to-end surfaces the same contradictions restated with more variants, plus two the ADLC Plan didn't have material to catch. This guide adopts ADLC Plan §15.3 as normative wherever it already ruled, and adds:

| Topic | Conflicting statements found in this source | Resolution adopted here |
|---|---|---|
| Memory layers (restated) | M0–M5 ("Multi Layer Memory", early pass) vs M0–M6 (RFC-0005, restated ~6×) | **M0–M6, RFC-0005 normative** (unchanged from ADLC Plan §15.3) |
| Cache layers (restated) | L1–L4 (early pass, no L0) vs L0–L6 ("Seven-Level" pass) vs L0–L5 (RFC-0005, restated ~8×) vs concrete-TTL L0–L5 (Sprint 2.2) | **L0–L5, RFC-0005 normative, TTLs from Sprint 2.2** (5 min / 1 h / 24 h / 7 d / 30 d / policy-controlled) — unchanged from ADLC Plan §15.3, TTLs newly pinned down |
| Identity/Trust service boundary | Every Sprint 3.1–3.2 pass treats **Identity Service** and **Trust Service** as two separate services; the Microservices-Implementation-Guide (built from the Volume 9 outline) merged them into one **Trust Authority** | **Keep the existing merge.** Re-splitting now would break already-built code (Instructional Manual §3.4) for a distinction the source itself doesn't defend — it's an artifact of different drafting passes, not a deliberate design choice. Not in scope for this guide. |
| Risk classification | Two independent 5-level taxonomies never reconciled with each other: **Safety S0–S4** (RFC-0007, informational→critical, drives human-oversight gating) vs **AI Assurance AIA-R0–R4** (EU AI Act framing, minimal→critical, drives assurance tier Bronze/Silver/Gold/Platinum) | **Both stay, mapped 1:1** (S0≈R0 … S4≈R4) rather than merged — they answer different questions (S = "does a human need to look at this response now", AIA-R = "what assurance tier must this *system* hold"). The SOA Connector Bus's governance check (§5) evaluates trust and S-class per call; AIA-R classification applies once, at connector-onboarding time. |
| Platform name | Title page: "Autonomous Enterprise Protocol eXtended"; from the investor-deck pass onward (~line 19,934): "Agent Ecosystem Protocol Exchange" | Cosmetic; not an architecture decision. Flagged here so it isn't silently "fixed" inconsistently across future documents — use whichever the current commercial materials (Handoff, ADLC Plan) use. |

**Scope discipline check.** Nine of this source's ~30 passes (Stages 9–20, "Autonomous Intelligence Internet," "Agent Operating System," "Planetary Intelligence Grid," "Singularity Framework," "AEP-X Zero — Version ∞") describe a self-evolving, planet-scale successor to the very platform being scoped in Weeks 1–12. None of that is designed here, in the SOA doc, the Microservices doc, or the code scaffolds — it is exactly the "everything looks equally urgent" failure mode the ADLC Plan's Critical Evaluation (§15.2.1) already flagged, one order of magnitude larger. This document is scoped to: the Universal Connector Layer, as an SOA-pattern addition to the already-committed 7-service microservices core, buildable in the Weeks 13+ window the Microservices-Implementation-Guide left open.

### 1.2 Cross-walk — what's genuinely new for architecture purposes

| Source concept | Status |
|---|---|
| Agent Registry, Trust Authority, Discovery, Memory, Workflow Engine, Safety Engine, Governance Engine | **Built / already designed** — Instructional Manual + Microservices-Implementation-Guide, unchanged |
| Universal Connector Layer (Enterprise/Industrial/Productivity/Developer/AI Platform/Gov-Edu connectors) | **New — designed in this document as SOA** |
| Knowledge Service, ML Integration Layer (Prediction/Learning/Optimisation Engines), Anti-Hallucination Engine V2 / Verification Engine, Universal Cost Optimiser | **New — designed in [Microservices-Architecture-v2.md](Microservices-Architecture-v2.md) as microservices** |
| Marketplace Engine, Certification Platform, Developer Portal | **Still backlog** — Handoff §2 deferral stands; not re-opened by this source |
| Stages 9–20 (AOS, AII, Planetary Intelligence Grid, Singularity Framework, etc.) | **Out of scope**, per §1.1 scope discipline check above |

---

## 2. Why SOA fits the Universal Connector Layer and not the core

Classic SOA/ESB architecture earns its coupling and mediation overhead when a system integrates with **external systems it does not own**, that speak **heterogeneous, often legacy protocols**, change on **release cycles measured in quarters or years**, and require **centralised governance** before any AEP-X agent is allowed to touch them. That is precisely the Universal Connector Layer's problem, not the AI-native core's:

| Property | AI-native core (Registry, Trust, Memory, Workflow, Safety, Governance) | Universal Connector Layer (SAP, Salesforce, Workday, OPC-UA plants, …) |
|---|---|---|
| Who owns the target system | AEP-X | External vendor / customer's existing estate |
| Protocol diversity | One (internal REST + Kafka, by design — Microservices Guide §4) | Many, simultaneously: SOAP, OPC-UA, proprietary RPC, REST, Modbus, GraphQL |
| Release cadence | Continuous (own the roadmap) | Vendor-controlled, often 6–18 months |
| Change unit that should deploy independently | One microservice | Usually a whole protocol family at once (e.g. all SAP calls need re-mediation if SAP's WSDL changes) |
| Governance requirement | Enforced once, in Governance Engine, per Law 8 (Auditability) | Enforced **per external system**, often per regulator (source's AIA-R classification is assigned per connector, not per microservice) |
| Failure blast radius if done as N independent microservices | N/A | N nearly-identical services, each re-implementing auth, retry, protocol translation, and audit — the "distributed monolith of adapters" anti-pattern |

Microservices optimise for independent deployability of *cohesive business capabilities you own*. The Connector Layer is the opposite shape: many external protocols funnelling into *one* set of AEP-X-side concerns (trust check, policy check, canonical message translation, audit). That's an Enterprise Service Bus's job description. Building 20+ near-identical FastAPI microservices — one per connector — for what is fundamentally one mediation concern repeated many times would itself be scope creep of the kind §15.2.1 warns about.

---

## 3. SOA Architecture — the AEP-X Connector Bus (ACB)

<!-- diagram: see SOA-Architecture.html for the rendered SVG -->

```
Client · SDK · CLI · MCP
        │
        ▼
   API Gateway  ───────────────────────────────┐
        │                                       │
        ▼                                       ▼
 Microservices core                    AEP-X Connector Bus (ACB)
 (Registry/Trust/Discovery/                     │
  Memory/Workflow/Safety/                       ├── Trust check  → Trust Authority (API)
  Governance — unchanged)                       ├── Policy check → Governance Engine (API)
                                                 ├── Canonical translation (RFC-0001 envelope)
                                                 └── Content-based routing
                                                        │
                        ┌───────────────┬───────────────┼───────────────┬────────────────┐
                        ▼               ▼               ▼               ▼                ▼
                 Enterprise      Industrial       Productivity     Developer        AI-Platform
                 Connector       Connector        Connector        Connector        Connector
                 Service         Service          Service          Service          Service
                 (SAP, SFDC,     (OPC-UA,         (Workspace,      (GitHub,         (OpenAI,
                 Dynamics,       Modbus,          M365, Slack,     GitLab, Jira,    Anthropic,
                 Oracle,         BACnet,          Teams, Zoom)     Confluence,      Gemini,
                 Workday,        SCADA, PLC)                       Azure DevOps)    Mistral,
                 ServiceNow)                                                        Ollama, vLLM,
                                                                                     HuggingFace)
                        │               │               │               │                │
                        ▼               ▼               ▼               ▼                ▼
                 [external systems, one adapter per system inside each coarse-grained service]
```

### 3.1 Design principles

1. **Coarse-grained services, fine-grained adapters.** One connector *service* per category (5 services), not one per external system (would be 25+). Inside each service, one `ProtocolAdapter`/`Connector` implementation per system — this reuses the source's own interfaces verbatim rather than inventing new ones:
   ```python
   class Connector:
       async def authenticate(self): pass
       async def discover(self): pass
       async def execute(self, request): pass
       async def monitor(self): pass
   ```
2. **Canonical message model, no exceptions.** Every connector service translates its external protocol (SOAP, OPC-UA, proprietary REST, etc.) into and out of the RFC-0001 message envelope before it touches the bus:
   ```json
   {
     "version": "1.0", "messageId": "uuid", "timestamp": "ISO8601",
     "sender": "aepx://agent/source", "receiver": "aepx://connector/sap",
     "messageType": "request", "payload": {}, "metadata": {}, "signature": "jwt"
   }
   ```
   This is the same envelope already used inside the microservices core — the Connector Bus is a *mediation pattern* laid over the same protocol, not a second, incompatible standard.
3. **Mediation, not choreography.** The core's Tier 2 services (Workflow/Safety/Governance) talk by publishing facts to Kafka (Microservices Guide §4.2 — choreography). The Connector Bus does the opposite on purpose: it centrally **orchestrates** trust check → policy check → protocol translation → routing → external call → response translation, because that is exactly the sequencing an external, ungoverned system needs enforced *before* every call, not eventually-consistent after it.
4. **Contract-first per connector.** Each connector service publishes a `Connector Contract` (the source's own term) describing what it bridges:
   ```yaml
   connector: sap-enterprise
   category: enterprise
   protocols_supported: [SOAP, REST]
   canonical_message: RFC-0001-v1.0
   governance_required: [trust_check, policy_check, audit]
   ai_risk_class: AIA-R2   # assigned at onboarding, per §1.1
   ```
5. **No connector calls another connector.** Cross-connector workflows (e.g. "look up the customer in Salesforce, then create a Workday ticket") are Workflow Engine's job, via the Gateway — the bus does not grow its own orchestration logic beyond mediation. This keeps the ESB from becoming the "smart pipes, dumb endpoints" anti-pattern SOA is often criticised for.

### 3.2 Service catalogue (SOA layer)

| Connector service | External systems owned | Protocols translated | Governance checks (every call) | Data store |
|---|---|---|---|---|
| **Enterprise Connector Service** | SAP, Salesforce, Microsoft Dynamics, Oracle, Workday, ServiceNow | SOAP, REST, proprietary RPC | Trust ≥ threshold (Trust Authority); Policy evaluate (Governance Engine); AIA-R classification enforced at onboarding | PostgreSQL (`connectors.enterprise.*` — credentials via Vault, not DB) |
| **Industrial Connector Service** | SCADA, PLC, OPC-UA endpoints, BACnet, Modbus devices | OPC-UA, Modbus, BACnet | Same, plus mandatory Safety Engine pre-check (industrial actions are physical-world side effects — Law 6 Human Authority applies to Safety-class systems) | PostgreSQL (`connectors.industrial.*`) |
| **Productivity Connector Service** | Google Workspace, Microsoft 365, Slack, Teams, Zoom | REST, OAuth2-fronted proprietary APIs | Trust check; Policy evaluate | PostgreSQL (`connectors.productivity.*`) |
| **Developer Tools Connector Service** | GitHub, GitLab, Jira, Confluence, Azure DevOps | REST, GraphQL (GitHub) | Trust check; Policy evaluate | PostgreSQL (`connectors.devtools.*`) |
| **AI Platform Connector Service** | OpenAI, Anthropic, Gemini, Mistral, Ollama, vLLM, HuggingFace | REST (each vendor's own schema) | Trust check; Policy evaluate; **Universal Cost Optimiser consulted before every call** (this is where LLM spend actually happens — Law 5, Reuse Before Computation) | PostgreSQL (`connectors.aiplatform.*`) |

Government/Education connectors named in the source (Digital Identity, Citizen Services, Universities, LMS, Research Networks) are **reference design only**, same status as Marketplace Engine — no named concrete system to integrate against yet, so no service is built for them in this pass.

### 3.3 The bus itself

`connector-bus/` (repo root, a sibling of `services/` — the Connector Bus mediates between the microservices core and external systems, so it isn't itself one of the owned microservices) — a single lightweight mediation service, **not** a commercial ESB product (MuleSoft/BizTalk-class tooling would itself be the over-engineering the ADLC Plan's "extremely low cost" positioning and Reality Validation Programme exist to prevent — see §6). It is a thin FastAPI service plus the existing Kafka bus already running for the microservices core:

- `POST /bus/route` — accepts an RFC-0001 envelope, does trust + policy check via HTTP calls to the existing Trust Authority and Governance Engine, resolves `receiver` (e.g. `aepx://connector/sap`) to the owning connector service, forwards, returns the translated response.
- Publishes `connector.invoked` / `connector.failed` events to the same Kafka bus Workflow/Safety/Governance already consume — Governance Engine's "consume every topic" audit pattern (Microservices Guide §4.2) extends to connector traffic for free, no new audit code.
- Content-based routing table is data, not code — a `connectors` table (`name`, `category`, `base_url`, `ai_risk_class`) so adding a 26th connector is a row insert plus a new adapter class, never a bus redeploy.

---

## 4. Security & compliance in the SOA layer

Reuses everything already specified for the core — no new security model:

- **AuthN/AuthZ:** OAuth2/OIDC + JWT (RFC-0002) for the calling agent; each connector service additionally holds its own vendor credentials in Vault, never in application config or the database.
- **mTLS** between Gateway → Connector Bus → connector services (Zero Trust, RA-0004).
- **Trust Before Execution (Law 2):** every `/bus/route` call resolves the calling agent's trust score via Trust Authority before mediation proceeds — a low-trust agent is rejected at the bus, before any external system is touched.
- **Evidence and audit:** every connector call and response is wrapped in the same `{answer, confidence, evidence[], verification_status}` contract the Safety Engine already enforces (Instructional Manual §4.4) when the connector's response feeds back into an agent's answer — e.g. a Salesforce lookup result counts as evidence with `source: "connector:salesforce"`.
- **AIA risk classification is per-connector, assigned once at onboarding** (§1.1), not re-evaluated per call — this is deliberately different from the S0–S4 safety classification, which *is* per call. Connectors touching Workday (HR/employment data) or any Industrial connector default to **AIA-R2 or higher**, which per the source's Assurance Levels requires at minimum **Silver** (Governance + Verification) before the connector is allowed to go live — do not skip this to hit a build-sequence date.

---

## 5. Build sequence addendum (Weeks 13+)

Follows the same dependency discipline as the Microservices-Implementation-Guide's Marketplace Engine deferral: **the Connector Bus depends on Trust Authority and Governance Engine already being healthy in production** — building it earlier would let ungoverned external calls through with no trust or policy check, the identical failure mode the Microservices Guide flagged for early Marketplace Engine builds.

| Week | Deliverable |
|---|---|
| 13 | Connector Bus skeleton (`/bus/route`, routing table, Kafka publish); no real connectors wired yet — verify with a mock connector only |
| 14 | AI Platform Connector Service — self-hosted/open-weights model server (Ollama or vLLM), not a commercial API — highest priority because it's on the Universal Cost Optimiser's critical path (§3.2); a metered commercial connector (OpenAI, Anthropic, etc.) is added later only if usage data shows the local tier needs supplementing |
| 15 | Developer Tools Connector Service (GitHub only, to start) |
| 16 | Productivity Connector Service (Slack only, to start) |
| 17–18 | Enterprise Connector Service (Salesforce only — do **not** build all six enterprise systems before validating the pattern on one; SAP/Dynamics/Oracle/Workday/ServiceNow follow only once Salesforce's AIA classification and governance gate are proven in production) |
| Backlog | Industrial Connector Service (needs a real OPC-UA target to build against — reference design only until a pilot names one, same status as Marketplace Engine) |

## 6. Definition of Done — SOA milestone

- `POST /bus/route` rejects a call when the calling agent's trust score is below the connector's configured threshold, and the rejection is visible in Governance Engine's `GET /audit` within 1 second.
- At least one live connector per category except Industrial (backlog) responds end-to-end: agent → Gateway → Connector Bus → connector service → external system (or its sandbox/mock) → response wrapped in the evidence contract.
- Every connector call appears in the audit log with `ai_risk_class` and `trust_score_at_call_time` recorded — this is what makes an AIA-R2+ connector's compliance story auditable after the fact, not just at onboarding.
- No connector service calls another connector service directly; all cross-connector workflows go through Workflow Engine.
- This milestone is recorded in `governance/decisions/`, explicitly noting that Government/Education and Industrial connectors remain reference-design-only and are not built.

---

*AEP-X — SOA Architecture Implementation Guide · Companion to ADLC-Plan, Handoff, Instructional-Manual, and Microservices-Implementation-Guide · 7 July 2026*
