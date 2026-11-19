---
name: aepx-rfcs-conformance
description: AEP-X RFCs (rfcs/RFC-0001…0008), how to write a new RFC in the repo's format, and the RFC-0007 conformance suite — the 12 checks, `aepx test`, and platform/conformance. Use when reading or drafting an RFC, or running, debugging or adding a conformance check.
---

# AEP-X RFCs and conformance

## The RFCs (`rfcs/`)

Every RFC is currently `Status: Draft`.

| RFC | One line |
|---|---|
| 0001 Core Protocol | The message envelope (version, messageId, timestamp, sender, receiver, messageType, payload, metadata), message types, and the `aepx://agent|tool|workflow|capability|memory|policy|connector/...` addressing scheme. |
| 0002 Identity & Trust | Trust Score = 20% each of Identity, Behaviour, Security, Evidence and Reputation (0–100). Six levels: Untrusted 0–19, Basic, Verified, Trusted 60–79, Highly Trusted, Certified 95–100. Seven identity types. |
| 0003 Messaging & Workflow | Kafka event topics and orchestration modes: Sequential is built; Parallel, Conditional and Dynamic are deferred. Choreography is used for cross-cutting concerns. |
| 0004 Discovery & Federation | Capability discovery ranked by 40% match + 25% trust + 15% availability − 10% latency − 10% cost. Federation levels F0–F5 are out of scope until post-GA. |
| 0005 Memory & Cache | The normative memory layers M0 Prompt … M6 Federated and cache layers L0 Prompt (5 min) … L5 Federation. Cache-first cost rules. |
| 0006 Blockchain Ecosystem | Adds the `blockchain` connector category, hash-chain audit anchoring, did:key identity, and the optional on-chain policy ceiling (`AEPXPolicyRegistry`). |
| 0007 SDK & Conformance | The SDK plugin contract with `aepx.plugins` entry points, the conformance check catalogue and report semantics, the CLI, and the Conformance and Workbench platforms. |
| 0008 AI ↔ Blockchain Bridge | Governed `contract_read`/`contract_write` (AI→chain), and the `AEPXOracle` plus `services/oracle-bridge` decision oracle (chain→AI). |

## Writing a new RFC

1. Copy `rfcs/_template.md` to `rfcs/RFC-00NN-<kebab-title>.md`, using the next number (0009 is next).
2. Fill in the header exactly as the existing RFCs do: `# RFC-00NN: <Title>`, `Status: Draft`, `Author(s):` and `Created: <d Month yyyy>`.
3. Keep the nine numbered sections in order: 1 Abstract, 2 Motivation, 3 Design Goals, 4 Specification (bold numbered sub-points like `**4.1 ...**`), 5 Data Model / Schema (link `schemas/sql/*.sql` or `schemas/openapi/*.yaml`, or say "None" and why), 6 Security & Compliance, 7 Backward Compatibility, 8 Reference Implementation (paths to services and files), 9 Open Questions.
4. Follow the house conventions the recent RFCs (0006–0008) use:
   - Name the Laws the change serves.
   - Keep a "zero external infrastructure by default, degrade cleanly, never a 5xx" design goal.
   - Make every addition additive and opt-in (Constitution Art. IV: no breaking changes within v1.x).
   - Name every env var the change introduces.
   - Record resolved open questions in §9 with a date.
5. Lifecycle is Draft → Review → Frozen → Deprecated (Constitution Art. IV). Moving an RFC's status is a governance step, so ask the user.
6. If the RFC adds normative behaviour, add a conformance check for it (below) and link the RFC from `README.md`.

## Conformance suite (RFC-0007)

Engine: `sdk/python/aepx/conformance/`. It uses only public APIs and creates throwaway entities only (`conformance-<hex>` trust entities and unregistered DIDs).

| ID | RFC | Checks |
|---|---|---|
| `core.envelope-shape` | RFC-0001 | the SDK envelope has every normative field and correct defaults (local, no network) |
| `core.envelope-routes` | RFC-0001 | invoking `ml` through the bus returns 200, or a governed 403/503 |
| `core.unknown-connector` | RFC-0001 | a random unknown connector returns 404 |
| `trust.default-score` | RFC-0002 | a fresh entity's trust is 50 |
| `trust.adjust` | RFC-0002 | behaviour adjusted 50 + 10 reads back as 60 |
| `governance.policy-ordinal` | Gov | the allowed set across S0..S4 is a prefix (ordinal-consistent) |
| `governance.audit-shape` | Gov | `/audit` is a list whose entries have topic and event |
| `did.roundtrip` | RFC-0006 | a minted did:key resolves to the same document |
| `did.malformed` | RFC-0006 | a malformed DID is rejected |
| `ledger.anchor-shape` | RFC-0006 | anchors carry the hash-chain fields |
| `ledger.verify` | RFC-0006 | an anchored ID verifies with `chain_valid=true`; an unanchored one reports `anchored=false` |
| `gateway.health` | Ops | every service in Gateway `/health` reports `status: ok` |

Results are PASS, FAIL or SKIP. Any exception, including an unreachable service, becomes SKIP. A deployment is **conformant** iff it has no FAIL results and at least one PASS.

### Running it

```bash
# CLI (exit 0 iff conformant), see aepx-cli for all flags
python cli/aepx_cli/__main__.py test [--check ID ...] [--json] [--gateway URL --bus URL ...]

# Conformance platform (:8082): browser UI, or the API
curl -X POST localhost:8082/runs -H 'Content-Type: application/json' -d '{"checks":["did.roundtrip"]}'
curl localhost:8082/checks ; curl localhost:8082/runs ; curl localhost:8082/runs/1

# Python
python -c "from aepx import AepxClient; from aepx.conformance import run_conformance; print(run_conformance(AepxClient()).to_dict())"
```

`gateway.health` fails if **any** service that the Gateway aggregates is not `ok`. So a new service wired into the Gateway must return `{"status": "ok"}` from `/health`.

### Adding a check

1. In `checks.py`, write `def _my_check(client) -> CheckResult` and decorate it with `@_skip_on_unreachable`. Return FAIL only when the target is reachable but non-conformant.
2. Append `ConformanceCheck("<area>.<name>", "RFC-00NN", "<title>", _my_check)` to `CHECKS`.
3. Add a fake-route test in `sdk/python/tests/test_conformance.py` for the conformant, non-conformant and unreachable cases. `test_fully_conformant_deployment_passes_every_check` must still pass, so extend its fake routes too.
4. Update RFC-0007 §4.2, which lists the catalogue. The CLI and `platform/conformance` pick up new checks automatically, but `platform/conformance` must be rebuilt, because it installs the SDK at image build time.

## Related skills

- `aepx-sdk` — the conformance engine's code
- `aepx-cli` — `aepx test`
- `aepx-consoles` — platform/conformance (:8082)
- `aepx-governance-policy` — Constitution lifecycle and governance sign-off
- `aepx-blockchain` — RFC-0006 and RFC-0008 implementation detail
