---
name: aepx-conn-blockchain
description: Blockchain connector service (connectors/blockchain) with 7 chain connectors, including a live generic EVM JSON-RPC adapter for `ethereum` (raw RPC, RFC-0008 contract_read/contract_write) and stubs for polygon, base, bitcoin, solana and others. Use when calling chains via the bus or changing the EVM adapter.
---

# Blockchain connectors (`connectors/blockchain`)

## Role

Public and permissioned ledgers (RFC-0006 §4.1). Six connectors are AIA-R2 / min trust 60; `hyperledger-fabric` is AIA-R1 / 50 (enterprise-permissioned, RFC-0006 §6). All are allowed by the S2 ceiling, but a never-seen agent has trust score 50 (Trust's default), so a connector with `min_trust_score` above 50 returns 403 `trust score 50 below required ...` until the agent's trust is higher. Because the connector is only reachable through the bus, a chain *write* is a governed action: it has passed trust, policy, circuit breaker and audit (RFC-0008 §4.1).

Risk classes in this category: AIA-R1 x1, AIA-R2 x6.

## Where

- Code: `connectors/blockchain/app/main.py` (routes) and `connectors/blockchain/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/blockchain/tests/test_health.py`. Deps: `connectors/blockchain/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0, web3==7.6.1).
- Compose service **`connector-blockchain`**, host port **8031** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. Compose sets `EVM_RPC_URL=${EVM_RPC_URL:-http://localhost:8545}`. Inside the container, localhost is not a chain, so by default the adapter degrades. The opt-in overlay `docker-compose.chain.yml` adds an `anvil` devnet, points `EVM_RPC_URL` at `http://anvil:8545` and supplies `EVM_PRIVATE_KEY` from env with a devnet default. See the three-step bring-up in that file's header.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "blockchain")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-blockchain:8000`, overridable with `CONNECTOR_URL_BLOCKCHAIN` on the connector-bus.

## Connectors

7 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `ethereum` | JSON-RPC | AIA-R2 | 60 | specialized |
| `polygon` | JSON-RPC | AIA-R2 | 60 | stub |
| `base` | JSON-RPC | AIA-R2 | 60 | stub |
| `avalanche` | JSON-RPC | AIA-R2 | 60 | stub |
| `bitcoin` | JSON-RPC | AIA-R2 | 60 | stub |
| `solana` | JSON-RPC | AIA-R2 | 60 | stub |
| `hyperledger-fabric` | gRPC | AIA-R1 | 50 | stub |

## Specialized adapters

### `ethereum`: `EVMRPCAdapter` (any EVM-compatible chain via `EVM_RPC_URL`)

Env: `EVM_RPC_URL` (default `http://localhost:8545`), `EVM_RPC_TIMEOUT` (seconds, default `5`), `EVM_PRIVATE_KEY` (optional, write signing only). RFC-0008 §6: the key is a production secret outside local dev, is never persisted and is never returned. All responses carry `source: "connector:ethereum"` and `rpc_url`. Any failure returns `_degraded(...)`: `result: "[fallback: <reason> — stub response for op '<op>']"`, `confidence: 0.3`, `maturity: "specialized_degraded"`. It never returns a 5xx.

| Mode | Trigger | Payload | Behaviour |
|---|---|---|---|
| Raw JSON-RPC | no `op` or any other `op` | `method` (default `eth_blockNumber`), `params` (default `[]`) | Pure httpx POST `{jsonrpc, id, method, params}`. `op` in the response = method. An RPC `error` degrades. Needs no web3. |
| `contract_read` | `op: "contract_read"` | `address`, `abi`, `function`, `args` (default `[]`) | `eth_call` via web3's ABI codec. Missing address/abi/function degrades. Result is made JSON-safe (bytes -> `0x` hex). |
| `contract_write` | `op: "contract_write"` | same as read | Needs `EVM_PRIVATE_KEY`. When unset it degrades with `EVM_PRIVATE_KEY unset — signing disabled`. When set it builds, signs and broadcasts the tx and returns `result: {tx_hash, from}`. |

`web3==7.6.1` is imported lazily (`_get_web3`), only for the contract ops. If it can't be imported, those ops degrade with `web3 not importable`.

The other 6 connectors (`polygon`, `base`, `avalanche`, `bitcoin`, `solana`, `hyperledger-fabric`) use `StubAdapter`. EVM chains like Polygon, Base and Avalanche are reachable today by pointing `ethereum`'s `EVM_RPC_URL` at them (adapter docstring).

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-blockchain", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `blockchain`, otherwise 404 `connector '<name>' is not registered in category 'blockchain'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/blockchain/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/blockchain
cd connectors/blockchain && python -m pytest tests -v
```

Tests: health, 7 catalogue entries, stub dispatch (`bitcoin`), unknown 404, `ethereum` degraded without RPC, `contract_read` degraded without RPC, `contract_read` with missing args, and `contract_write` without a key (`signing disabled`). On-chain contract integration is a separate CI job: `pip install -r tests/requirements.txt && python -m pytest tests/test_contracts.py -v`. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8031/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/ethereum","payload":{"method":"eth_blockNumber","params":[]}}'
```

Without a chain, `response.maturity` is `specialized_degraded`. With the chain overlay it returns the block number. A fresh agent (trust 50) gets 403 on trust. For local stub debugging only, `localhost:8031/connector/execute` bypasses governance. The oracle-bridge and console reach this service through the bus (console also sets `CONNECTOR_URL_BLOCKCHAIN`).

## Adding a real adapter here

- A non-EVM chain (`bitcoin`, `solana`, `hyperledger-fabric`) needs its own adapter class with its own `*_RPC_URL`-style env var. It must degrade the way `_degraded` does. RFC-0006/0008 require zero-infrastructure defaults and never a 5xx.
- Any signing key comes only from env, is never logged or returned, and a missing key must produce an explicit degraded reason (RFC-0008 §6). Never commit keys, including devnet ones, into skills or docs.
- Keep web3 lazy. Its import cost is why `_get_web3` exists.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
- `aepx-blockchain`: ledger anchoring, contracts, oracle-bridge and the chain overlay (RFC-0006/0008).
