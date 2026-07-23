# RFC-0008: AI ↔ Blockchain Bridge — Governed Contract Calls and the Decision Oracle

Status: Draft
Author(s): AEP-X Founding Team
Created: 23 July 2026

## 1. Abstract

Makes the protocol bidirectional between agentic AI and blockchains. **AI→chain:** an agent reads or writes a smart contract as an ordinary *governed* connector action, so a state-changing transaction passes the same trust + policy + circuit-breaker gate as any other connector call. **chain→AI:** an on-chain `AEPXOracle.sol` caller requests an AI decision, and an off-chain bridge (`services/oracle-bridge`) runs a governed AI call plus an evidence/verification scoring pass and writes the scored answer back on-chain.

## 2. Motivation

RFC-0006 added a `blockchain` connector category, on-chain audit anchoring, `did:key` identity, and an optional on-chain policy ceiling — but every one of those is the platform *using* a chain for its own governance. It left the two directions an application actually wants unbuilt: an agent that needs to *act on* a chain (pay, register, vote, settle), and a contract that needs to *ask* an AI something (a data feed, a classification, a judgement) and get a trustworthy answer back. A raw signing key bolted onto an agent would give the first while bypassing Law 2 (Trust Before Execution) and Law 8 (Auditability); a naive oracle would give the second while writing unverified model output on-chain as if it were fact. This RFC does both *through* the platform's existing governance rather than around it.

## 3. Design Goals

Same discipline as RFC-0006: every new capability works with **zero external infrastructure by default** and degrades cleanly (never a 5xx) when a chain isn't configured or is unreachable. A chain write with no signing key, a contract read against a cold RPC endpoint, and an oracle decision made while the AI or Verification service is down must all return a well-formed, clearly-reasoned degraded response — mirroring `connectors/blockchain`'s existing `EVMRPCAdapter` fallback and `services/governance`'s Postgres fallback. Nothing here requires infrastructure the reference stack can't itself stand up and unit-test.

## 4. Specification

**4.1 AI→chain — governed contract read/write.** `connectors/blockchain/app/adapters.py`'s `EVMRPCAdapter` gains two ops on top of its existing raw JSON-RPC path:

- `{"op": "contract_read", "address", "abi", "function", "args"}` — an `eth_call` through the ABI codec; no gas, no key.
- `{"op": "contract_write", "address", "abi", "function", "args"}` — a signed, broadcast transaction; requires `EVM_PRIVATE_KEY` on the connector, and degrades with an explicit `signing disabled` reason when unset.

Because the connector is only reachable through the Connector Bus (`connector-bus`), both ops inherit the bus's trust check (Law 2), policy check (Law 8, and the `blockchain` category's `AIA-R2`/min-trust-60 default from RFC-0006), circuit breaker, and `connector.invoked`/`connector.failed` audit events. That is precisely what makes a chain *write* a *governed* action rather than a raw key operation — there is no ungoverned path to a signature.

**4.2 chain→AI — the decision oracle.** `governance/contracts/AEPXOracle.sol` is a minimal request/fulfil contract: `requestDecision(prompt)` emits `DecisionRequested(requestId, requester, prompt)`; `fulfillDecision(requestId, answer, confidence, band)` is restricted to a single authorized `oracle` address and can fulfil each request once. `services/oracle-bridge` is the off-chain fulfiller. Its pipeline, shared by an always-on HTTP endpoint (`POST /oracle/decide`) and the on-chain listener:

1. **Governed AI call** — routes an RFC-0001 envelope through the Connector Bus to the `ml` connector (`ORACLE_AI_CONNECTOR`, default `ml`), so the model call is trust/policy/audit-governed like any other; the bridge never calls a model directly.
2. **Evidence scoring** — sends the answer to the Verification Engine (`POST /verify`), whose truth score becomes the on-chain `confidence` (0–100) and whose `GREEN`/`AMBER`/`RED`/`GREY` band is written alongside it. The bridge writes a *scored* answer, never a raw completion.
3. **Write-back** — when a chain is configured, calls `fulfillDecision` with the scored result and publishes `oracle.requested`/`oracle.fulfilled` to Kafka for Governance to audit.

The on-chain listener runs only when `ORACLE_RPC_URL`, `ORACLE_CONTRACT_ADDRESS`, and `ORACLE_PRIVATE_KEY` are all set; otherwise it idles and `POST /oracle/decide` still serves the full off-chain pipeline.

**4.3 Audit coverage.** `services/governance/app/main.py`'s `_CONSUMED_TOPICS` adds `oracle.requested` and `oracle.fulfilled` — without this, those events would be silently dropped from the audit trail (the same exact-topic-match trap RFC-0006's brain topics hit); a Governance drift-guard test asserts their presence.

**4.4 SDK.** Two built-in plugins (RFC-0007 plugin architecture): `client.chain.read/write/rpc` (AI→chain, delegating to the connectors plugin so the governed path is unavoidable) and `client.oracle.decide/poll/history` (chain→AI, over the oracle-bridge).

## 5. Data Model / Schema

None. The `AEPXOracle.sol` contract is the durable record of fulfilled decisions when a chain is configured; Governance's existing `audit_log` (via the two new Kafka topics) is the durable record otherwise. `oracle-bridge` keeps only an in-memory recent-history list (`GET /oracle/history`) as an operator convenience — deliberately no new SQL table, per this repo's "extend later, don't front-load" rule.

## 6. Security & Compliance Considerations

`EVM_PRIVATE_KEY` (AI→chain writes) and `ORACLE_PRIVATE_KEY` (chain→AI fulfilment) are production secrets if ever set outside local development, and are never persisted server-side or returned by any endpoint — the same posture as `IDENTITY_JWT_SECRET` and RFC-0006's `LEDGER_PRIVATE_KEY`. `fulfillDecision` is permissioned to a single `oracle` address so no third party can forge an AI answer on-chain; the address must match the account behind `ORACLE_PRIVATE_KEY` or the call reverts. AI→chain writes remain bounded by Governance's `max_risk_level` ceiling exactly as RFC-0006 left it — nothing here raises what the platform already permits. The oracle writes an evidence-derived `confidence`/`band` rather than presenting model output as fact, keeping Law 3 (Evidence Before Assertion) intact even for on-chain consumers.

## 7. Backward Compatibility

Every addition is additive and opt-in. The `EVMRPCAdapter`'s raw JSON-RPC path (and its existing test) is unchanged — the new ops are dispatched only on an explicit `op` field. `oracle-bridge` is a new service; no existing service depends on it. Both new SDK plugins are appended to the built-in list; the existing five are unaffected, and the entry-point discovery set simply grows. No existing env var, endpoint, schema, or audit-trail shape changes when the new `ORACLE_*`/`EVM_PRIVATE_KEY` vars are unset.

## 8. Reference Implementation

`connectors/blockchain/app/adapters.py` (contract_read/contract_write), `governance/contracts/AEPXOracle.sol`, `services/oracle-bridge/`, `services/governance/app/main.py` (`_CONSUMED_TOPICS`), `sdk/python/aepx/plugins/chain.py`, `sdk/python/aepx/plugins/oracle.py`.

## 9. Open Questions

Whether the oracle listener should move from id-polling to log-based event subscription (`eth_getLogs`/filters) once an EVM devnet is added to `docker-compose.yml` for CI (RFC-0006 §9's deferred question) — id-polling is deterministic and web3-version-robust, which is why it ships first; a high-throughput deployment would prefer filters. Deferred until the on-chain path is exercised in CI rather than only unit-tested.
