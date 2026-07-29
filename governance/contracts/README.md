# Governance reference contracts (RFC-0006, RFC-0008)

These Solidity sources are reference implementations, not something this repo compiles, deploys, or runs automatically — consistent with how the 96 stub connectors work (docs/Connector-Catalogue.md): the code path exists and degrades cleanly when unconfigured, and swapping in the real thing is a deliberate, credentialed, day-2 operation, not a code change.

- **`AEPXAnchor.sol`** (RFC-0006) — append-only Merkle-root anchor. `services/governance/app/ledger.py`'s `EVMAnchorClient` calls `anchor(bytes32)` on this contract when configured.
- **`AEPXPolicyRegistry.sol`** (RFC-0006) — on-chain `maxRiskLevel` ceiling. `services/governance/app/ledger.py`'s `read_onchain_max_risk_level()` reads it when configured.
- **`AEPXOracle.sol`** (RFC-0008) — chain→AI request/fulfil oracle. `requestDecision(prompt)` emits `DecisionRequested`; the `services/oracle-bridge` service watches for it, runs a *governed* AI call (Connector Bus → `ml`) plus a Verification scoring pass, and calls the permissioned `fulfillDecision(id, answer, confidence, band)` to write the answer back. The bridge works with zero chain configured (its `POST /oracle/decide` runs the same pipeline off-chain); the contract is only the on-chain rendezvous point.

## Deploying (any EVM-compatible chain, including a local devnet)

1. Compile with Foundry (`forge build`) or Hardhat — any standard Solidity 0.8.24 toolchain.
2. Deploy to a local devnet (e.g. `anvil`), a public testnet, or any EVM-compatible chain (Ethereum, Polygon, Base, Avalanche, ...) you control.
3. Point Governance at the deployment:

   | Env var | Purpose |
   |---|---|
   | `LEDGER_RPC_URL` | JSON-RPC endpoint for both contracts |
   | `LEDGER_CONTRACT_ADDRESS` | deployed `AEPXAnchor` address |
   | `LEDGER_PRIVATE_KEY` | key Governance signs anchor transactions with |
   | `POLICY_CONTRACT_ADDRESS` | deployed `AEPXPolicyRegistry` address |

   For `AEPXOracle`, point the **oracle-bridge** service (not Governance) at the deployment:

   | Env var | Purpose |
   |---|---|
   | `ORACLE_RPC_URL` | JSON-RPC endpoint for the oracle contract |
   | `ORACLE_CONTRACT_ADDRESS` | deployed `AEPXOracle` address |
   | `ORACLE_PRIVATE_KEY` | key the bridge signs `fulfillDecision` with (must equal the contract's `oracle` address) |

   The `oracle` address passed to `AEPXOracle`'s constructor must match the account behind `ORACLE_PRIVATE_KEY`, or `fulfillDecision` reverts with `not oracle`.

Leaving all of these unset (the default) is fully supported: Governance falls back to the local SHA-256 hash chain for anchoring and the in-process seed policy for risk-level enforcement, and the oracle-bridge simply serves its off-chain `POST /oracle/decide` pipeline with its on-chain listener idle — nothing here is required for the platform to run.
