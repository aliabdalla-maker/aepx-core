# aepx-core — AEP-X reference implementation

The buildable monorepo for AEP-X: a universal, cache-first, evidence-first interoperability layer for agentic AI. This is the real repo the [Instructional Manual](docs/Instructional-Manual.html) describes — governance, RFCs, schemas, and 14 services, runnable with one `docker compose up`.

## Documentation

Planning and architecture documents live in [`docs/`](docs/), in read order:

1. [ADLC-Plan](docs/ADLC-Plan.md) — the reconciled development lifecycle, including the Critical Evaluation (§15) that every scope decision in this repo traces back to.
2. [Handoff](docs/Handoff.html) — committed Year-1 scope and blockers.
3. [Instructional-Manual](docs/Instructional-Manual.html) — the step-by-step build runbook this repo's `services/registry`, `identity`, `trust`, `memory`, `cache`, `gateway` implement.
4. [Microservices-Implementation-Guide](docs/Microservices-Implementation-Guide.html) — adds `discovery`, `workflow`, `safety`, `governance`.
5. [SOA-Architecture](docs/SOA-Architecture.html) — the Universal Connector Layer, implemented here as `connector-bus/` + `connectors/`.
6. [Microservices-Architecture-v2](docs/Microservices-Architecture-v2.html) — adds `knowledge`, `verification`, `cost-optimiser`, `ml-integration`, and the L0–L5 cache upgrade.
7. [Hybrid-Architecture-and-Comparison](docs/Hybrid-Architecture-and-Comparison.html) — why the platform uses both a microservices core and an SOA integration layer.
8. [Operational-Manual](docs/Operational-Manual.html) ([PDF](docs/Operational-Manual.pdf)) — running, verifying, and troubleshooting the live stack, with UML use case and sequence diagrams of the three load-bearing flows.
9. [Connector-Catalogue](docs/Connector-Catalogue.md) — all 100 connectors by category, with risk class and maturity.

The original source attachment is kept at [`attachment/AEP-X Ultra v2 (source).docx`](attachment/AEP-X%20Ultra%20v2%20%28source%29.docx) for traceability.

## Repository layout

```
aepx-core/
├── governance/              constitution.md, book-of-laws.md, decisions/
├── rfcs/                     RFC-0001 – RFC-0005 (Tier 1 Foundation Standards)
├── schemas/
│   ├── sql/                  001_init.sql, 002_v2_additions.sql, 003_connectors.sql
│   └── openapi/              per-service OpenAPI contracts
├── services/
│   ├── registry/ identity/ trust/ memory/ cache/ gateway/      (Instructional Manual)
│   ├── discovery/ workflow/ safety/ governance/                (Microservices-Implementation-Guide)
│   └── knowledge/ verification/ cost-optimiser/ ml-integration/ (Microservices-Architecture-v2)
├── console/                   the LLM / machine-learning box — web GUI (chat + file/folder/image/video upload), http://localhost:8080
├── connector-bus/            AEP-X Connector Bus — SOA mediation layer (SOA-Architecture.md)
├── connectors/                catalogue.json (100 connectors) + 10 category services:
│                              enterprise/ productivity/ devtools/ aiplatform/ data/
│                              messaging/ industrial/ cloud/ government/ education/
├── sdk/python/aepx/          `pip install aepx`; `from aepx import Agent`
├── cli/aepx_cli/              `aepx init|create|run|deploy`
├── docker-compose.yml         the whole stack, one command
├── .github/workflows/ci.yml   matrixed tests across every service
└── docs/                      all planning & architecture documents
```

## Running it

```bash
docker compose up --build
curl http://localhost:8000/health   # Gateway health-check aggregates every service
```

To bring up just the SOA layer after the core is healthy (per SOA-Architecture.md §5's dependency ordering):

```bash
docker compose up -d trust governance
docker compose up --build connector-bus enterprise-salesforce aiplatform-openai devtools-github productivity-slack
```

## Running the tests

Every service is independently testable — see `.github/workflows/ci.yml` for the exact matrix. Locally, from any `services/<name>/` or `connectors/<name>/` directory:

```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

`services/cache` and `services/discovery` additionally need `fakeredis` (see `services/cache/requirements-dev.txt`).

## What's built vs. what's deliberately not

**Built:** all 14 core services, health-checked and tested; the Connector Bus plus **100 catalogued connectors across 10 category services** (see [docs/Connector-Catalogue.md](docs/Connector-Catalogue.md)). Four connectors have specialized adapters (Salesforce, self-hosted ML/Ollama, GitHub, Slack); the other 96 are routed, trust-checked, policy-gated stubs — swap a stub for a real adapter class in the category service's `adapters.py` when credentials exist; nothing else changes. High-risk categories (industrial AIA-R3, government AIA-R3) are policy-denied by default under Governance's `max_risk_level: S2` seed policy — raising that ceiling is an explicit governance decision, not a code change.

**Deliberately not built** (see docs for the reasoning, not an oversight):
- Marketplace Engine — backlog per Handoff §2.
- Real integrations for the 96 stub connectors — each needs credentials, a sandbox, and (for AIA-R2+) its assurance-tier sign-off before its stub is replaced (SOA-Architecture.md §4). The original "one per category first" sequencing was widened to the full 100-connector catalogue by explicit owner decision (July 2026).
- Everything in the source manual's Stages 9–20 (Autonomous Intelligence Internet, Agent Operating System, Planetary Intelligence Grid, "AEP-X Zero — Version ∞") — out of scope by design; see SOA-Architecture.md §1.1's scope discipline check.

---
*Prepared 7 July 2026 · Equality Software Ltd / AEP-X Programme*
