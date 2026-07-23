# aepx-core — AEP-X reference implementation

The buildable monorepo for AEP-X: a universal, cache-first, evidence-first interoperability layer for agentic AI. This is the real repo the [Instructional Manual](docs/Instructional-Manual.html) describes — governance, RFCs, schemas, and 15 services (14 core + the RFC-0008 oracle bridge), runnable with one `docker compose up`.

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
9. [Connector-Catalogue](docs/Connector-Catalogue.md) — all 107 connectors by category, with risk class and maturity.

RFC-0006 ([rfcs/RFC-0006-blockchain-ledger.md](rfcs/RFC-0006-blockchain-ledger.md)) adds the `blockchain` connector category, Governance's tamper-evident audit anchoring, `did:key` decentralized identity, and optional smart-contract policy enforcement — see [`governance/contracts/`](governance/contracts/) for the reference Solidity sources.

RFC-0008 ([rfcs/RFC-0008-ai-blockchain-bridge.md](rfcs/RFC-0008-ai-blockchain-bridge.md)) makes the protocol **bidirectional between AI and blockchains**. *AI→chain:* agents read/write smart contracts as ordinary governed connector actions (`connectors/blockchain`'s `contract_read`/`contract_write` ops — trust + policy + audit apply to a signed transaction like any other connector call). *chain→AI:* an on-chain `AEPXOracle.sol` caller requests an AI decision, and the [`services/oracle-bridge`](services/oracle-bridge/) service runs a governed AI call (via the bus → `ml`) plus a Verification scoring pass and writes the evidence-scored answer back on-chain. Both directions degrade cleanly with zero chain configured; drive them from the SDK via `client.chain.*` and `client.oracle.*`, or from the **AEP-X Console** (below).

The original source attachment is kept at [`attachment/AEP-X Ultra v2 (source).docx`](attachment/AEP-X%20Ultra%20v2%20%28source%29.docx) for traceability.

## Repository layout

```
aepx-core/
├── governance/              constitution.md, book-of-laws.md, decisions/, contracts/ (RFC-0006/0008 Solidity)
├── rfcs/                     RFC-0001 – RFC-0008 (Foundation Standards, blockchain ecosystem, SDK/conformance, AI↔chain bridge)
├── schemas/
│   ├── sql/                  001_init.sql, 002_v2_additions.sql, 003_connectors.sql
│   └── openapi/              per-service OpenAPI contracts
├── services/
│   ├── registry/ identity/ trust/ memory/ cache/ gateway/      (Instructional Manual)
│   ├── discovery/ workflow/ safety/ governance/                (Microservices-Implementation-Guide)
│   ├── knowledge/ verification/ cost-optimiser/ ml-integration/ (Microservices-Architecture-v2)
│   └── oracle-bridge/                                          (RFC-0008 chain→AI decision oracle)
├── console/                   the LLM / machine-learning box — web GUI (chat + file/folder/image/video upload), http://localhost:8080
├── connector-bus/            AEP-X Connector Bus — SOA mediation layer (SOA-Architecture.md)
├── connectors/                catalogue.json (107 connectors) + 11 category services:
│                              enterprise/ productivity/ devtools/ aiplatform/ data/
│                              messaging/ industrial/ cloud/ government/ education/ blockchain/
├── sdk/python/aepx/          `pip install aepx`; Agent + AepxClient, plugin architecture
│                              (did/connectors/trust/ledger/audit/chain/oracle + `aepx.plugins` entry points),
│                              and the RFC-0007 conformance engine (aepx.conformance)
├── cli/aepx_cli/              `aepx init|create|run|deploy|test|did|invoke|plugins`
├── platform/
│   ├── workbench/             utilisation platform — developer portal, http://localhost:8081
│   ├── conformance/           testing platform — RFC conformance runs, http://localhost:8082
│   └── aepx-console/          one live GUI over the WHOLE platform, http://localhost:8083
├── docker-compose.yml         the whole stack, one command
├── .github/workflows/ci.yml   matrixed tests across every service
└── docs/                      all planning & architecture documents
```

## Running it

```bash
docker compose up --build
curl http://localhost:8000/health   # Gateway health-check aggregates every service
```

Then open the **AEP-X Console** at **[http://localhost:8083](http://localhost:8083)** — one live GUI for **both the AEP-X protocol and the blockchain**: an overview health grid of every service, the connector catalogue + governed invoke, trust & did:key identity, memory / discovery / workflows, governance + audit + ledger, ML/Brain, and an LLM box on the protocol side; and a first-class **Blockchain** workspace on the other — live node status (block / chain-ID / gas), governed smart-contract read/write, the RFC-0008 AI↔chain decision oracle, and a raw JSON-RPC console. Every action routes through the same governed path and lands in the live audit feed. (The focused GUIs remain: LLM box at :8080, Workbench at :8081, Conformance at :8082.)

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

**Built:** all 14 core services plus the RFC-0008 `oracle-bridge`, health-checked and tested; the Connector Bus plus **107 catalogued connectors across 11 category services** (see [docs/Connector-Catalogue.md](docs/Connector-Catalogue.md)). Five connectors have specialized adapters (Salesforce, self-hosted ML/Ollama, GitHub, Slack, generic-EVM-RPC/ethereum) — the `ethereum` adapter now also does governed `contract_read`/`contract_write` (RFC-0008 AI→chain), not just raw JSON-RPC; the other 102 are routed, trust-checked, policy-gated stubs — swap a stub for a real adapter class in the category service's `adapters.py` when credentials exist; nothing else changes. High-risk categories (industrial AIA-R3, government AIA-R3) are policy-denied by default under Governance's `max_risk_level: S2` seed policy — raising that ceiling is an explicit governance decision, not a code change (or, per RFC-0006, an on-chain `AEPXPolicyRegistry.sol` decision, if configured).

Governance additionally anchors its audit trail (Law 8) with a local SHA-256 hash chain, and Identity issues `did:key` decentralized identities (Law 1) — both work with zero external infrastructure by default, with an optional upgrade path to a real EVM chain (see [`governance/contracts/README.md`](governance/contracts/README.md)).

Per RFC-0007 ([rfcs/RFC-0007-sdk-conformance.md](rfcs/RFC-0007-sdk-conformance.md)), the SDK carries a plugin architecture (five built-ins plus third-party discovery via the `aepx.plugins` entry-point group) and a protocol conformance engine, surfaced three ways: `aepx test` in the CLI, the **Conformance testing platform** (http://localhost:8082), and the **Workbench utilisation platform** (http://localhost:8081) for exercising envelopes, DIDs, trust, the ledger, and the audit trail interactively.

**Deliberately not built** (see docs for the reasoning, not an oversight):
- Marketplace Engine — backlog per Handoff §2.
- Real integrations for the 96 stub connectors — each needs credentials, a sandbox, and (for AIA-R2+) its assurance-tier sign-off before its stub is replaced (SOA-Architecture.md §4). The original "one per category first" sequencing was widened to the full 100-connector catalogue by explicit owner decision (July 2026).
- Everything in the source manual's Stages 9–20 (Autonomous Intelligence Internet, Agent Operating System, Planetary Intelligence Grid, "AEP-X Zero — Version ∞") — out of scope by design; see SOA-Architecture.md §1.1's scope discipline check.

---
*Prepared 7 July 2026 · Equality Software Ltd / AEP-X Programme*
