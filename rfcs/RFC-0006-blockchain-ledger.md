# RFC-0006: Blockchain Ecosystem — Connectors, Ledger Anchoring, DID, Policy Contracts

Status: Draft
Author(s): AEP-X Founding Team
Created: 21 July 2026

## 1. Abstract

Adds a `blockchain` connector category, tamper-evident audit anchoring for the Governance Engine, `did:key` decentralized identity for agents, and an optional on-chain source of truth for the risk-level policy ceiling.

## 2. Motivation

Law 8 (Auditability) requires every action to generate a record, but a record stored only in one Postgres instance is only as tamper-evident as that instance's access controls. Law 1 (Identity Before Interaction) requires a stable identity, but the platform's identities have so far only been platform-issued, not independently verifiable. Both gaps are exactly what blockchain-native techniques (hash chains, self-certifying identifiers, on-chain state) are for — this RFC applies them without requiring every deployment to run a chain.

## 3. Design Goals

Every new capability must work with **zero external infrastructure by default** and degrade cleanly (never a 5xx) when an optional chain isn't configured or is unreachable — the same discipline already used throughout the platform (`connectors/aiplatform/app/adapters.py`'s `SelfHostedMLAdapter`, `services/trust/app/main.py`'s Postgres fallback). Nothing in this RFC should require infrastructure the reference implementation can't itself stand up and test.

## 4. Specification

**4.1 Connector category — `blockchain`.** Seven catalogued connectors (`ethereum`, `polygon`, `base`, `avalanche`, `bitcoin`, `solana`, `hyperledger-fabric`), routed and governed identically to every other category (SOA-Architecture.md §3.1). `ethereum` is specialized via a generic EVM JSON-RPC adapter (works against any EVM-compatible chain, including a local devnet, via `EVM_RPC_URL`); the rest are stubs pending real credentials/sandboxes, per the existing 96-stub precedent.

**4.2 Ledger anchoring.** `services/governance/app/ledger.py`'s `LocalHashChainAnchor` computes, every 20 audit-log rows, a Merkle root over that batch and chains it to the previous anchor's hash (`anchor_hash = sha256(prev_hash + merkle_root)`) — always on, no dependency. `EVMAnchorClient` optionally also submits that root to an `AEPXAnchor.sol` deployment when `LEDGER_RPC_URL`/`LEDGER_CONTRACT_ADDRESS`/`LEDGER_PRIVATE_KEY` are set. `GET /ledger/verify/{audit_id}` replays the chain from genesis to prove (or disprove) that history hasn't been altered since anchoring.

**4.3 Decentralized identity — `did:key`.** `services/identity/app/did.py` generates an Ed25519 keypair, multicodec-prefixes the public key (`0xed01`), and multibase-encodes it (base58btc) into `did:key:z6Mk...` — a fully self-certifying identifier: `GET /did/{did}` resolves it into a W3C DID Document by decoding the string alone, no registry or chain lookup required. `services/registry` mints one automatically for any agent that doesn't supply its own at registration (fail-open if Identity is unreachable).

**4.4 Smart-contract policy enforcement.** `services/governance/app/main.py`'s `evaluate_policy` tries `ledger.read_onchain_max_risk_level()` (a read against an `AEPXPolicyRegistry.sol` deployment) before falling back to the in-process `_POLICIES["max_risk_level"]` seed — unconfigured behaviour is unchanged.

## 5. Data Model / Schema

`schemas/sql/007_blockchain.sql`: widens `connectors.registry`'s category `CHECK`, seeds the 7 new catalogue rows, adds `governance.ledger_anchors`, adds `agents.did`.

## 6. Security & Compliance Considerations

Private keys minted by `POST /did` are returned once and never persisted server-side (same posture as `IDENTITY_JWT_SECRET`) — callers own safekeeping them; this is a reference implementation, not a custody solution. `LEDGER_PRIVATE_KEY` (for the optional EVM anchor submitter) must be treated as a production secret if ever set outside local development. The `blockchain` category defaults every connector to `AIA-R2`/min-trust-60 (`hyperledger-fabric` at `AIA-R1`/50, being enterprise-permissioned rather than public) — still governed by the existing `max_risk_level: S2` ceiling, so nothing here is reachable above what Governance already permits.

## 7. Backward Compatibility

Every addition here is additive and opt-in: existing `/policy/evaluate` behaviour, the audit trail's shape (aside from an added `id` field), and agent registration all work identically when the new env vars are unset. `agents.did` is nullable; no existing row needs a backfill.

## 8. Reference Implementation

`connectors/blockchain/`, `services/governance/app/ledger.py`, `services/identity/app/did.py`, `services/registry/app/main.py`'s `_mint_did`, `governance/contracts/`.

## 9. Open Questions

Whether a real EVM devnet (e.g. an `anvil` service) should eventually be added to `docker-compose.yml` so the on-chain paths get exercised in CI rather than only unit-tested against an unconfigured/mocked client — deferred until there's a concrete need to exercise the on-chain path itself, per this repo's "extend later, don't front-load" rule.
