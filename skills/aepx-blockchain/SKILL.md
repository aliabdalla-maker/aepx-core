---
name: aepx-blockchain
description: AEP-X blockchain layer (RFC-0006/RFC-0008) — Solidity contracts (AEPXAnchor, AEPXPolicyRegistry, AEPXOracle), deploy_contracts.py, anvil live-chain mode, test_contracts.py, ledger anchoring, did:key, contract_read/contract_write, oracle-bridge. Use when touching chain code or running live-chain mode.
---

# AEP-X blockchain layer (RFC-0006, RFC-0008)

Design rule for both RFCs: **zero chain by default, degrade cleanly and never return a 5xx.** Every on-chain path is opt-in, controlled by env vars. With no chain configured, Governance uses a local SHA-256 hash chain and the in-process seed policy, the ethereum adapter returns a `specialized_degraded` stub result, and the oracle-bridge serves `/oracle/decide` with its listener idle.

## Pieces and where they live

| Piece | File(s) | Enabled by |
|---|---|---|
| Audit anchoring (Law 8) | `services/governance/app/ledger.py`, `main.py` | always local; EVM if `LEDGER_RPC_URL` + `LEDGER_CONTRACT_ADDRESS` + `LEDGER_PRIVATE_KEY` are set |
| On-chain policy ceiling | `ledger.read_onchain_max_risk_level()` | `LEDGER_RPC_URL` + `POLICY_CONTRACT_ADDRESS` |
| did:key identity (Law 1) | `services/identity/app/did.py`, registry `_mint_did` | always on |
| AI→chain contract calls | `connectors/blockchain/app/adapters.py` `EVMRPCAdapter` | `EVM_RPC_URL`; writes also need `EVM_PRIVATE_KEY` |
| chain→AI decision oracle | `services/oracle-bridge/app/main.py` | listener needs `ORACLE_RPC_URL` + `ORACLE_CONTRACT_ADDRESS` + `ORACLE_PRIVATE_KEY` |
| Contracts | `governance/contracts/*.sol` (pragma `^0.8.24`) | deployed by `scripts/deploy_contracts.py` |

**Contracts**
- `AEPXAnchor`: `anchor(bytes32)` appends a root and emits `Anchored`. Also exposes `latestRoot()` (reverts with `no anchors yet` when empty) and `anchorCount()`.
- `AEPXPolicyRegistry(uint8 initial)`: `maxRiskLevel` is an ordinal where 0 = S0 and 4 = S4. `setMaxRiskLevel` is `onlyOwner` and must be ≤ 4.
- `AEPXOracle(address oracle)`: `requestDecision(prompt)` emits `DecisionRequested`. `fulfillDecision(id, answer, confidence<=100, band)` is `onlyOracle` and can fulfil each request once. Also `getDecision`, `isFulfilled`, and `setOracle` (`onlyOwner`).

## Ledger anchoring and did:key

Every 20 `governance.audit_log` rows (`_ANCHOR_BATCH_SIZE`), Governance computes a Merkle root over `event_hash(id, topic, event)` and chains it with `anchor_hash = sha256(f"{prev_hash}:{root}")`, starting from genesis `"0"*64`. The result is stored in `governance.ledger_anchors`, or in an in-memory fallback without Postgres. `EVMAnchorClient.anchor(root)` also submits the root on-chain when configured, and returns `None` on any failure. `GET /ledger/verify/{audit_id}` replays the chain from genesis and reports `anchored` and `chain_valid`.

did:key is an Ed25519 key with multicodec prefix `0xed01`, base58btc-encoded as `did:key:z6Mk...`. `POST /did` returns the private key once and never stores it. `GET /did/{did}` decodes the DID into a W3C DID Document with no lookup, and returns 400 for a malformed DID.

## AI→chain: contract_read / contract_write

The payload goes to connector `ethereum` through the bus, as `{"op": "contract_read"|"contract_write", "address", "abi", "function", "args"}`. A payload without `op` is treated as raw JSON-RPC `{"method", "params"}`. SDK: `client.chain.read/write/rpc`. The catalogue entry is `AIA-R2` with `min_trust_score` 60, so a fresh sender (default trust 50) is **denied by the trust gate** until its trust reaches 60. Degraded reasons are explicit, for example `EVM_PRIVATE_KEY unset — signing disabled` or `web3 not importable`.

## chain→AI: oracle-bridge flow

1. A contract or EOA calls `AEPXOracle.requestDecision(prompt)`, which emits `DecisionRequested`.
2. The listener runs every `ORACLE_POLL_INTERVAL` seconds (default 15), or on demand via `POST /oracle/poll`. It reads logs from the last scanned block (`ORACLE_USE_LOGS=true` by default) and falls back to scanning every ID via `nextRequestId`.
3. `decide()` publishes `oracle.requested`, then makes a governed AI call. That call is an envelope from `aepx://agent/oracle-bridge` to `aepx://connector/${ORACLE_AI_CONNECTOR:-ml}` via `CONNECTOR_BUS_URL`.
4. Verification `POST /verify` scores the answer. Its truth score becomes `confidence` (0–100) and its band is one of GREEN, AMBER, RED or GREY. Any failure along the way gives GREY / 0 with a reason.
5. The bridge calls `fulfillDecision` (its signer must equal the contract's `oracle` address, or the call reverts with `not oracle`), then publishes `oracle.fulfilled`. Governance audits both topics (`_CONSUMED_TOPICS`).

Off-chain only: `POST /oracle/decide {"prompt": ...}`, or `client.oracle.decide(...)`.

## Run live-chain mode end to end

```bash
pip install -r tests/requirements.txt       # web3, py-solc-x, eth-tester, py-evm for the host-side deploy
docker compose -f docker-compose.yml -f docker-compose.chain.yml up -d anvil    # chain-id 31337, 2s blocks, :8545
python scripts/deploy_contracts.py --rpc http://localhost:8545
docker compose --env-file .env.chain -f docker-compose.yml -f docker-compose.chain.yml up --build
```

What the deploy script does:
- Compiles the contracts with solc 0.8.24, installing it if missing.
- Deploys with anvil account #0, or `--private-key` / `DEPLOYER_PRIVATE_KEY`. It seeds `AEPXPolicyRegistry` with 2 (S2, matching the seed policy) and sets the oracle address to the deployer.
- Writes `governance/contracts/deployed-addresses.json` and `.env.chain`.
- With no `--rpc`, it only deploys to an in-memory EVM and prints the addresses.

The overlay points governance, oracle-bridge and connector-blockchain at `http://anvil:8545` and sets `EVM_PRIVATE_KEY`, defaulting to anvil key #0. Verify in the aepx-console Blockchain section (`:8083`), or with `curl localhost:8015/health` (`chain_configured: true`).

Note: `governance/contracts/README.md` still says the repo does not compile or deploy these contracts. That predates `deploy_contracts.py` and the CI `contracts` job (see RFC-0008 §9).

## Changing a contract safely

1. Edit the `.sol` file. Keep it in step with the hand-written Python ABIs, which are **not** generated: `_ANCHOR_ABI` / `_POLICY_ABI` in `services/governance/app/ledger.py` and `_ORACLE_ABI` in `services/oracle-bridge/app/main.py`. A renamed function or a changed signature silently degrades to `None`/fallback, because every chain call swallows exceptions.
2. If you change a constructor, update `deploy_all()` in `scripts/deploy_contracts.py`.
3. Run `pip install -r tests/requirements.txt && python -m pytest tests/test_contracts.py -v`. This is the CI `contracts` job, on an in-memory EVM. Add a test for any new behaviour, including access-control reverts.
4. Run the governance, oracle-bridge and connectors/blockchain unit tests to confirm the no-chain path is unchanged.
5. Redeploy to anvil. Contracts are immutable, so a change needs a new deployment and a fresh `.env.chain`.
6. Anything that changes `maxRiskLevel` semantics, or who may call `setMaxRiskLevel` / `fulfillDecision`, is a governance decision. Get the user's sign-off (see `aepx-governance-policy`).

Keys (`LEDGER_PRIVATE_KEY`, `ORACLE_PRIVATE_KEY`, `EVM_PRIVATE_KEY`) are production secrets outside local development. Never commit `.env.chain` values for a real chain.

## Related skills

- `aepx-governance-policy` — risk ceiling, audit trail, and decision process
- `aepx-sdk` — `client.chain.*`, `client.oracle.*`, `client.ledger.*`, `client.did.*`
- `aepx-conn-blockchain`, `aepx-connector-adapter` — the blockchain connector category and its adapters
- `aepx-svc-governance`, `aepx-svc-identity`, `aepx-svc-oracle-bridge` — owning services
- `aepx-consoles` — the Blockchain section at :8083
- `aepx-database` — `governance.ledger_anchors`, `agents.did` (007_blockchain.sql)
