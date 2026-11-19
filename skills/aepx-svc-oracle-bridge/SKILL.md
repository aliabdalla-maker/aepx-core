---
name: aepx-svc-oracle-bridge
description: Oracle Bridge for AEP-X (RFC-0008), the chain→AI decision oracle. It runs a governed AI call through the Connector Bus, scores the answer with Verification, and optionally fulfils AEPXOracle.sol requests on-chain. Use when working on, debugging, calling or extending the oracle-bridge service in aepx-core.
---

# Oracle Bridge service (`services/oracle-bridge`)

## Role
This is the off-chain half of the RFC-0008 chain→AI bridge. For each decision it:
1. Routes an RFC-0001 envelope through the Connector Bus to the `ml` connector. The bridge never talks to a model directly, so Law 2 (Trust Before Execution) and Law 8 (Auditability) apply.
2. Scores the answer through the Verification Engine.
3. When a chain is configured, writes the scored answer back through `AEPXOracle.fulfillDecision`.

Writing an evidence-derived confidence and band, rather than a raw completion, keeps Law 3 intact (RFC-0008 §6). The service is designed to degrade cleanly and never return a 5xx (RFC-0008 §3).

## Where
- Code: `services/oracle-bridge/app/main.py`. Contract: `governance/contracts/AEPXOracle.sol`.
- Compose service `oracle-bridge`, host port **8015** -> container 8000, `depends_on: [connector-bus, verification, kafka]`.
- The chain overlay `docker-compose.chain.yml` sets `ORACLE_RPC_URL=http://anvil:8545` and adds `anvil`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"oracle-bridge", chain_configured, ai_connector, decisions_seen}` |
| POST | `/oracle/decide` | Runs the full pipeline off-chain; always available | `DecideIn`: `{prompt: str, request_id: int \| null}`. Returns `{request_id, prompt, answer, confidence (0-100 int), band (GREEN\|AMBER\|RED\|GREY), ai_source, reason, ts}` |
| GET | `/oracle/history?limit=50` | Recent decisions, newest first | A list of decision dicts |
| POST | `/oracle/poll` | Runs one on-chain poll cycle | With no chain configured: `{chain_configured:false, processed:0, reason}`. Otherwise `{chain_configured, mode:"logs"\|"ids", processed, scanned_to_block \| total_requests}`, or `{..., processed:0, reason:"connect_failed (...)"\|"poll_failed (...)"}` |

## Configuration
| Name | Default (code) | Meaning |
|---|---|---|
| `CONNECTOR_BUS_URL` | `http://connector-bus:8000` | Bus for the governed AI call (`POST /bus/route`) |
| `VERIFICATION_URL` | `http://verification:8000` | Scoring (`POST /verify`) |
| `ORACLE_AI_CONNECTOR` | `ml` | Connector name in the envelope `receiver` (`aepx://connector/<name>`) |
| `ORACLE_RPC_URL` | unset | EVM JSON-RPC endpoint |
| `ORACLE_CONTRACT_ADDRESS` | unset | `AEPXOracle` address |
| `ORACLE_PRIVATE_KEY` | unset | Signs `fulfillDecision`. It must match the contract's `oracle` address, or the call reverts with `not oracle`. Supply it from the environment only |
| `ORACLE_POLL_INTERVAL` | `15` | Seconds between listener cycles |
| `ORACLE_USE_LOGS` | `true` | Scans `DecisionRequested` logs from the last block. On error it falls back to scanning every request id |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Broker for `oracle.*` events |

The listener thread runs only when all three `ORACLE_*` connection vars (RPC URL, contract address, private key) are set. Otherwise it exits immediately.

## Data & dependencies
- **Storage:** only an in-memory `_HISTORY`, capped at 200. There is deliberately no SQL table (RFC-0008 §5). The durable records are the chain and Governance's audit log.
- **Bus call:** the envelope is `{version:"1.0", sender:"aepx://agent/oracle-bridge", receiver, messageType:"request", payload:{prompt}, metadata:{}}`, with a 30 s timeout. The bridge reads `response.result` and `response.source`. A non-200 reply (for example a trust, policy or circuit 403/503) becomes a reason of the form `ai_call_denied (<code>): <detail>`.
- **Verify call:** `{workflow_id:"oracle-<request_id|adhoc>", claims:[{text: answer, source_ids:[ai_source]}]}`. The bridge reads `summary.truth_score` (clamped and rounded to 0–100) and `summary.confidence_band`.
- **Degrading:**
  - With no answer, the result is `0/GREY`, reason `no_answer_to_verify`.
  - With Verification down, the result is `0/GREY`, reason `verification_unreachable (...)`.
  - With the bus unreachable, the reason is `ai_call_unreachable (...)`.
- **Kafka (publishes):**
  - `oracle.requested` with `{request_id, prompt[:500], ts}` on every decision
  - `oracle.fulfilled` with `{request_id, band, confidence, tx_hash, ts}` only after an on-chain write
  - Governance consumes both.
- **On-chain:** a minimal ABI with `nextRequestId`, `getDecision`, `fulfillDecision` and the `DecisionRequested` event. A request that is already fulfilled is skipped. web3 is imported lazily.
- **With the current Verification scaffold** (35 points per source id), a single-source answer scores 35, which is band GREY. Expect GREY until Verification's scoring changes.

## Run & test
```bash
pip install -r services/oracle-bridge/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/oracle-bridge
cd services/oracle-bridge && python -m pytest tests -v
```
The tests run with no bus, Verification or chain, and assert the GREY/0 degraded path. The happy path monkeypatches `_governed_ai_call` and `_verify`. The contract itself is tested in `tests/test_contracts.py` at the repo root (see aepx-blockchain).

Run on its own:
```bash
cd services/oracle-bridge && CONNECTOR_BUS_URL=http://localhost:8020 VERIFICATION_URL=http://localhost:8011 \
  uvicorn app.main:app --port 8015
curl -s localhost:8015/health
curl -s -X POST localhost:8015/oracle/decide -H 'Content-Type: application/json' -d '{"prompt":"Is 2+2=4?"}'
curl -s -X POST localhost:8015/oracle/poll
curl -s "localhost:8015/oracle/history?limit=5"
```

## Changing it
- `decide()` must never raise. Both the HTTP endpoint and the on-chain listener depend on always getting a well-formed decision, and `test_decide_degrades_clean_when_downstreams_unreachable` guards this.
- `confidence` must stay an int from 0 to 100 because it is written as `uint8`. `band` is written as a string.
- If you change the ABI, keep it in sync with `governance/contracts/AEPXOracle.sol`, `scripts/deploy_contracts.py` and `tests/test_contracts.py`.
- If you add or rename a Kafka topic, update Governance `_CONSUMED_TOPICS` and `test_consumes_oracle_bridge_topics` in the same change.
- Callers that depend on the response shapes:
  - `sdk/python/aepx/plugins/oracle.py` (`decide`, `poll`, `history`; its default URL is `http://localhost:8015`)
  - `platform/aepx-console` (`/api/oracle/*`)
  - the gateway health aggregate
- Never log or return `ORACLE_PRIVATE_KEY`, and never commit a real key. For the anvil overlay, the key and contract addresses come from the generated `.env.chain`, passed with `--env-file`, which `scripts/deploy_contracts.py --rpc http://localhost:8545` writes.
- There is no OpenAPI contract in `schemas/openapi/`.
- To find callers: `grep -rn "ORACLE_BRIDGE_URL\|/oracle/" services connector-bus sdk platform console`.

## Related skills
- aepx-blockchain: AEPXOracle, deploying to anvil, contract tests
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-verification: scoring
- aepx-svc-governance: audits `oracle.*`
- aepx-svc-brain: circuit breaker on the `ml` connector
- aepx-connector-adapter: the aiplatform `ml` connector
- aepx-governance-policy: the policy gate on the AI call
