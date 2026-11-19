---
name: aepx-svc-governance
description: Governance Engine for AEP-X — risk-level policy checks, the Kafka-fed audit trail (Law 8) and tamper-evident ledger anchoring (RFC-0006). Use when working on, debugging, calling or extending the governance service in aepx-core, or when audit events go missing.
---

# Governance Engine service (`services/governance`)

## Role
Governance has two jobs. It answers policy questions (`POST /policy/evaluate`, a risk-level ceiling check), and it consumes a fixed list of Kafka topics without conditions to build the platform audit trail. The Book of Laws says this is how Law 8 (Auditability) is enforced. It also anchors that trail in a tamper-evident way (RFC-0006): a local SHA-256 hash chain over batches of audit rows is always on, and anchoring on an EVM chain through `AEPXAnchor.sol` is optional.

## Where
- Code: `services/governance/app/main.py` (API, Kafka consumer, anchoring) and `app/ledger.py` (hashing, Merkle root, EVM clients).
- Compose service `governance`, host port **8009** -> container 8000. `depends_on: [kafka, postgres]`.
- The chain overlay `docker-compose.chain.yml` sets `LEDGER_RPC_URL=http://anvil:8545` and adds `anvil` to `depends_on`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"governance", persisted: bool}`. `persisted` is true when Postgres is reachable |
| POST | `/policy/evaluate` | Risk-level ceiling check | **Query param** `risk_level` (`S0`–`S4` or `AIA-R0`–`AIA-R4`). Returns `{risk_level, allowed, max_risk_level}`. For an unknown label it returns `{risk_level, allowed:false, reason:"unrecognised risk level"}` with HTTP 200 |
| GET | `/audit?limit=200` | Audit trail, newest first | `[{id, topic, event, recorded_at(epoch float)}]` |
| GET | `/ledger/anchors?limit=50` | Anchors, newest first | `[{seq_no, prev_hash, merkle_root, anchor_hash, entry_count, first_audit_id, last_audit_id, backend, tx_ref, anchored_at}]` |
| GET | `/ledger/verify/{audit_id}` | Replays the hash chain from genesis up to the anchor that covers `audit_id` | `{audit_id, anchored, chain_valid, anchor}`. When the id is not anchored yet: `anchored:false, chain_valid:null, anchor:null` |

Policy logic: `AIA-R` labels are mapped to `S` labels. The request is allowed when the requested index is at or below the ceiling. The ceiling comes from `ledger.read_onchain_max_risk_level()` when that is configured; otherwise it is the seed policy `_POLICIES = {"max_risk_level": "S2"}`.

## Configuration
| Name | Default (code) | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://aepx:aepx_dev_only@postgres:5432/aepx` | Audit and anchor storage |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Broker for the audit consumer (not set in compose) |
| `LEDGER_RPC_URL` | unset | EVM JSON-RPC endpoint, used for both on-chain anchoring and the on-chain policy |
| `LEDGER_CONTRACT_ADDRESS` | unset | `AEPXAnchor` address |
| `LEDGER_PRIVATE_KEY` | unset | Key that signs anchor transactions. Supply it only from the environment and never commit it |
| `POLICY_CONTRACT_ADDRESS` | unset | `AEPXPolicyRegistry` address. `maxRiskLevel()` (uint8) is read as the ceiling |

On-chain anchoring needs all three `LEDGER_*` vars. The on-chain policy needs `LEDGER_RPC_URL` and `POLICY_CONTRACT_ADDRESS`.

## Data & dependencies
- **Postgres:** `governance.audit_log` (schemas/sql/004_governance_audit.sql) and `governance.ledger_anchors` (schemas/sql/007_blockchain.sql).
- **In-memory fallback:** when Postgres is down, `_AUDIT_FALLBACK` and `_LEDGER_FALLBACK` are used, so audit writes never crash the consumer. That state is lost on restart.
- **Kafka (consumes), `_CONSUMED_TOPICS`:** `workflow.completed`, `safety.flagged`, `verification.completed`, `connector.invoked`, `connector.failed`, `trust.updated`, `brain.service_down`, `brain.service_recovered`, `brain.ollama_rewarmed`, `brain.circuit_opened`, `brain.circuit_closed`, `brain.circuit_half_open`, `oracle.requested`, `oracle.fulfilled`. The consumer uses `auto_offset_reset="earliest"` and runs in a daemon thread. If it errors, it waits 5 s and reconnects.
- **Anchoring:** after each write, once 20 rows (`_ANCHOR_BATCH_SIZE`) are unanchored, it computes a Merkle root over `event_hash(id, topic, event)`. It then computes `anchor_hash = sha256(prev_hash:root)` (genesis is `"0"*64`) and, when configured, sends `anchor(bytes32)` on-chain. Every anchoring exception is swallowed, so an anchoring failure never looks like a failed audit write. `tx_ref` is null unless the EVM submission succeeds.
- **web3** is imported lazily, so a Governance that never uses a chain does not pay the import cost. Every on-chain helper returns `None` on any failure, and the local chain and seed policy are then used.
- Calls no other AEP-X service.

## Run & test
```bash
pip install -r services/governance/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/governance
cd services/governance && python -m pytest tests -v
```
Tests run without Postgres or Kafka and exercise the in-memory fallback. `test_verify_detects_tampering` corrupts the shared fallback state on purpose, so it must stay last in `test_ledger.py`.

Run on its own:
```bash
cd services/governance && uvicorn app.main:app --port 8009
curl -s localhost:8009/health
curl -s -X POST "localhost:8009/policy/evaluate?risk_level=AIA-R2"
curl -s "localhost:8009/audit?limit=10"
curl -s localhost:8009/ledger/anchors
curl -s localhost:8009/ledger/verify/1
```

## Changing it
- **Topic drift is the known bug class.** `KafkaConsumer` matches exact topic names. When a producer adds a topic (a new `brain.<kind>` in `services/brain`, a new `oracle.*` in `services/oracle-bridge`, and so on), add it to `_CONSUMED_TOPICS`. Also update the drift-guard tests in `tests/test_health.py`. For brain, also update the `CHECK` in `schemas/sql/006_brain.sql`.
- `risk_level` is a **query parameter**, not a JSON body. Callers depend on that and on the `allowed` key:
  - `connector-bus/app/main.py` treats a non-200 response or a missing `allowed` as a deny (fail-closed).
  - `services/marketplace` (`_check_policy`)
  - `sdk/python/aepx/plugins/audit.py`
  - `platform/aepx-console` (`/api/policy`)
- `/audit` response shape and newest-first order are relied on by:
  - `services/brain` (`_recompute_reliability_and_circuits` reads `topic`, `event.connector` and `event.outcome`)
  - `console/app/main.py`
  - `sdk/python/aepx/plugins/audit.py`
  - `platform/workbench` and `platform/aepx-console`
- `/ledger/*` shapes are used by `sdk/python/aepx/plugins/ledger.py` and the workbench and console ledger panels.
- Keep `event_hash`, `merkle_root` and `LocalHashChainAnchor.anchor` deterministic. Changing them invalidates every stored anchor (`chain_valid` becomes false).
- `/policy/evaluate` does not write an audit row. Only Kafka events are audited.
- There is no OpenAPI contract for this service in `schemas/openapi/` (only `registry.yaml` exists).
- To find callers: `grep -rn "policy/evaluate\|/audit\|ledger/" services connector-bus sdk platform console`.

## Related skills
- aepx-governance-policy: changing risk ceilings and policy rules
- aepx-blockchain: `AEPXAnchor`, `AEPXPolicyRegistry`, and the anvil overlay
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-brain: publishes `brain.*` topics and reads `/audit`
- aepx-svc-oracle-bridge: publishes `oracle.*` topics
- aepx-svc-verification: `verification.completed`
- aepx-svc-marketplace: calls `/policy/evaluate`
