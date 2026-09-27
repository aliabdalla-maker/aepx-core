---
name: aepx-architecture
description: Entry point for aepx-core — whole-platform map. Covers the request path (gateway → services → connector bus → connectors), service dependencies from *_URL env vars, which Law each layer enforces, degrade-clean design, and which skill to use next. Use first when orienting in AEP-X.
---

# AEP-X architecture: platform map

AEP-X is an interoperability layer for agentic AI. It has a **microservices core** (18 FastAPI services under `services/`) and an **SOA integration layer**: `connector-bus/` plus 11 category services under `connectors/`, fronting 107 catalogued connectors. On top of those sit the SDK and CLI and four web GUIs. All of it runs from `docker compose up --build`. Every app listens on port 8000 in its container. Host ports are listed in `aepx-run-stack` and `aepx-new-service`.

## Layers

| Layer | Components |
|---|---|
| Clients | `sdk/python/aepx` (Agent, AepxClient + plugins), `cli/aepx_cli`, and the GUIs `console` (:8080), `workbench` (:8081), `conformance` (:8082), `aepx-console` (:8083) |
| Edge | `gateway` (:8000): aggregate `/health`, plus `/execute`, which is currently a passthrough (it fetches the agent from Registry) |
| Tier 1, synchronous | identity, trust, registry, memory, cache, discovery |
| Tier 2, event-driven over Kafka | workflow, safety, governance |
| v2 additions | knowledge, verification, cost-optimiser, ml-integration, brain |
| Business and bridge | marketplace, billing, oracle-bridge (RFC-0008) |
| SOA layer | `connector-bus` (:8020) → `connector-<category>` (:8021–8031) → adapter (specialized, or `StubAdapter`) |
| Infrastructure | postgres (pgvector), redis, neo4j, kafka (KRaft), ollama; optional anvil via `docker-compose.chain.yml` |

## The governed request path

The Connector Bus is the structural enforcement point. The SDK's `connectors`/`chain` plugins, the CLI's `invoke`, every GUI's chat and invoke, and oracle-bridge's AI calls all go through it:

```
client ──RFC-0001 envelope──► connector-bus POST /bus/route
   1. catalogue lookup (connectors/catalogue.json)      unknown → 404
   2. Trust  GET /trust/{sender-id}   < min_trust_score → 403 trust_below_threshold   (Law 2)
   3. Governance POST /policy/evaluate?risk_level=AIA-Rn  denied → 403 policy_denied  (Law 8 / ceiling S2)
   4. Brain  GET /brain/circuit/{name}  open → 503 (Brain unreachable → fail open)
   5. POST {CONNECTOR_URL_<CATEGORY> or http://connector-<category>:8000}/connector/execute
   6. Kafka connector.invoked / connector.failed ──► governance audit_log ──► ledger anchor every 20 rows
   7. Trust behaviour +1 on success (best-effort)
```

Other event flows:
- workflow publishes `workflow.completed`; safety consumes it and publishes `safety.flagged`.
- brain publishes `brain.*` and oracle-bridge publishes `oracle.*`.
- Governance consumes every topic listed in `_CONSUMED_TOPICS` into the audit trail.

## Service-to-service dependencies

Derived from `*_URL` env vars in `docker-compose.yml` plus each service's `os.getenv` defaults.

| Service | Calls |
|---|---|
| gateway | identity, trust, registry, memory, cache, discovery, workflow, safety, governance, knowledge, verification, cost-optimiser, ml-integration, oracle-bridge, connector-bus. Compose also sets `MARKETPLACE_URL` and `BILLING_URL`, which the code does not read. |
| registry | identity (mints a did:key, fail-open), postgres |
| discovery | registry, trust (code defaults), redis |
| workflow | registry, memory (code defaults), kafka |
| cost-optimiser | trust |
| marketplace | trust, governance |
| oracle-bridge | connector-bus, verification, kafka; optional `ORACLE_RPC_URL` |
| connector-bus | trust, governance, brain, `connector-<category>` (override with `CONNECTOR_URL_<CATEGORY>`), kafka |
| brain | governance, ollama (`OLLAMA_URL`), postgres; health-polls `MONITORED_SERVICES` |
| governance | postgres, kafka; optional `LEDGER_*`, `POLICY_CONTRACT_ADDRESS` |
| trust | postgres |
| cache | redis (`REDIS_HOST`) |
| connector-aiplatform | ollama (`OLLAMA_URL`, `OLLAMA_MODEL=llama3.2:1b`) |
| connector-blockchain | `EVM_RPC_URL`, optional `EVM_PRIVATE_KEY` |
| billing | Stripe only, gated on `STRIPE_API_KEY` |
| identity, memory, knowledge, verification, ml-integration, safety | no service URLs (safety uses kafka) |
| console | connector-bus, registry, trust, governance |
| workbench, conformance | gateway, identity, trust, registry, governance, connector-bus |
| aepx-console | all of the above plus brain, marketplace, billing, oracle-bridge, connector-blockchain |

## Which layer enforces which Law

| Law | Where it is enforced |
|---|---|
| 1 Identity Before Interaction | identity (tokens, did:key); registry mints DIDs |
| 2 Trust Before Execution | trust scores (RFC-0002), checked structurally by connector-bus; marketplace publish gate (trust ≥ 60 and policy allow) |
| 3 Evidence Before Assertion | verification (truth score and band); safety flags `no_evidence`; oracle writes scored answers only |
| 4 Knowledge Before Generation | knowledge service |
| 5 Reuse Before Computation | cache (L0–L5), cost-optimiser routing (`/route/decide`) |
| 6 Human Authority | S3/S4 require a human (Constitution Art. V); billing leaves payment to a human on Stripe |
| 7 Explainability | cost-optimiser's `explanation` for every routing decision |
| 8 Auditability | governance consumes every topic; ledger hash-chain anchoring |
| 9 Learning | ml-integration; brain learns circuit reliability from audit history |
| 10 Evolution | database-per-service schemas; independently deployable, independently tested components |

## Degrade-clean philosophy

Every optional dependency is off by default, and its absence gives a well-formed answer, **never a 5xx**. Examples:
- Governance and trust fall back to in-memory state without Postgres.
- The bus fails open when the Brain is unreachable.
- The chain paths return `specialized_degraded` results or idle, and billing returns `configured: false`.
- The GUIs return 502 with a reason.
- Conformance SKIPs unreachable subsystems.

Gates are the exception. A 403 or 503 from the bus is a designed outcome. Never work around one in code (Operational Manual §8.3–8.4).

## Where to start

| Task | Skill |
|---|---|
| Run or smoke-test the stack | `aepx-run-stack` |
| Test a component the CI way / fix red CI / Jenkins | `aepx-test-component`, `aepx-ci-debug`, `aepx-jenkins` |
| Work on one service | `aepx-svc-<name>` (e.g. `aepx-svc-gateway`, `aepx-svc-governance`, `aepx-svc-oracle-bridge`) |
| Add a new service | `aepx-new-service` |
| Bus routing and gates | `aepx-connector-bus` |
| Add or upgrade a connector; a category | `aepx-connector-adapter`, `aepx-conn-<category>` |
| SDK, plugins, CLI | `aepx-sdk`, `aepx-cli` |
| GUIs | `aepx-consoles` |
| Chain, contracts, oracle, did:key, ledger | `aepx-blockchain` |
| Laws, policy ceiling, audit, governance decisions | `aepx-governance-policy` |
| RFCs and conformance | `aepx-rfcs-conformance` |
| SQL, migrations, local data stores | `aepx-database` |
| Which document says what | `aepx-docs` |

## Related skills

All of the skills in the table above. Start with `aepx-run-stack` to get a live stack, then use `aepx-governance-policy` for the rules the platform enforces.
