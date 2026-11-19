---
name: aepx-governance-policy
description: AEP-X governance — constitution, the Ten Laws, the max_risk_level seed policy and AIA-R/S risk classes, policy evaluation, audit trail, and how to propose a policy or governance decision. Use when asked about Laws, policy denials, risk ceilings, audit, or changing governance rules.
---

# AEP-X governance and policy

Sources: `governance/constitution.md`, `governance/book-of-laws.md`, `services/governance/app/main.py`, `docs/SOA-Architecture.md` §1.1 and §4, and Operational Manual §6 and §8.

> **Raising a risk ceiling, lowering a connector's `min_trust_score`, or loosening any gate is a governance decision. It is not a code change.** Do not make it on your own initiative, and do not "fix" a 403 by editing a check. Draft the decision and get the user's explicit sign-off first.

## Constitution (v1.0 draft)

- **Preamble / Art. I**: AEP-X is a universal, low-cost, evidence-first interoperability layer. Every decision must be auditable, explainable and governed, and AEP-X never bypasses human authority in financial, legal, healthcare or child-related decisions.
- **Art. II**: the Ten Laws, defined in `book-of-laws.md`.
- **Art. III**: governance structure is interim (founder plus advisor). A Technical Steering Committee is targeted for Month 18.
- **Art. IV**: standards lifecycle is Draft → Review → Frozen → Deprecated, with no breaking changes within v1.x.
- **Art. V**: final human authority for financial, legal, healthcare and child-related decisions. This corresponds to S3/S4, where human oversight is mandatory.
- **Art. VI**: amendments are founder-approved, with an explicit rationale recorded in `governance/decisions/`, until the TSC exists.

## The Ten Laws (book-of-laws.md)

1. **Identity Before Interaction**: nothing participates without an identity.
2. **Trust Before Execution**: no action runs without a trust evaluation. The Connector Bus enforces this structurally.
3. **Evidence Before Assertion**: every claim needs evidence, a confidence score and a verification status.
4. **Knowledge Before Generation**: the order is Knowledge → Memory → Reasoning → Generation, never reversed.
5. **Reuse Before Computation**: the order is Cache → Memory → Workflow → Tool → Inference. This is the core economic law.
6. **Human Authority**: a human has final say in healthcare, government, finance, education and safety-critical domains (S3/S4).
7. **Explainability**: every decision answers why, how, on what evidence, and which alternatives were considered.
8. **Auditability**: every action records who, what, when, where, why and the outcome. Governance consumes every event topic.
9. **Learning**: Experience → Knowledge → Learning → Improvement. ML Integration closes this loop.
10. **Evolution**: any component can be upgraded, replaced or retired without breaking the whole.

## Risk classes and policy evaluation

- There are two 5-level taxonomies, mapped 1:1 and deliberately kept separate (SOA §1.1):
  - **Safety S0–S4**: evaluated per call. Answers "does a human need to look at this now?"
  - **AI Assurance AIA-R0–R4**: EU-AI-Act framing, assigned once per connector at onboarding. Drives the assurance tier (Bronze, Silver, Gold or Platinum). AIA-R2 and above needs at least Silver (Governance plus Verification) before going live.
- `POST /policy/evaluate?risk_level=X` accepts either `S0`–`S4` or `AIA-R0`–`AIA-R4`. `AIA-R` labels are mapped to `S` by ordinal. The request is allowed iff its index ≤ `max_risk_level`. The response is `{risk_level, allowed, max_risk_level}`. An unrecognised label returns `allowed: false`.
- The **seed policy** is `_POLICIES = {"max_risk_level": "S2"}` in `services/governance/app/main.py`. If `LEDGER_RPC_URL` and `POLICY_CONTRACT_ADDRESS` are set, `AEPXPolicyRegistry.maxRiskLevel()` wins. The deploy script seeds that contract to 2 (S2).
- Effect today: the 11 `AIA-R3` connectors (all 8 in industrial, plus 3 in government) get **403 policy_denied** at the bus. That is working as designed. The bus checks trust first (`min_trust_score` per connector in `connectors/catalogue.json`), then policy, then the Brain's circuit breaker.
- SDK: `client.audit.policy("AIA-R3")`.

## Audit trail (Law 8)

Governance runs a background Kafka consumer over an explicit topic list, `_CONSUMED_TOPICS`:
- workflow, safety and verification events
- `connector.invoked` / `connector.failed`
- `trust.updated`
- the `brain.*` topics
- `oracle.requested` / `oracle.fulfilled`

Each event is written to `governance.audit_log`, or to an in-memory fallback without Postgres, and anchored every 20 rows (see `aepx-blockchain`). Read it with `GET /audit?limit=N` (default 200) or `client.audit.tail()`. A producer that adds a new topic must also add it to `_CONSUMED_TOPICS`, because topics are matched exactly and unlisted events are dropped silently.

## Proposing a policy or governance decision (process)

1. **State the change and its scope.** For example: "raise `max_risk_level` S2 → S3", "lower `min_trust_score` for X", "promote AIA-R2 connector Y to live", or "amend Law N".
2. **Write the rationale.** Cover which Law(s) it affects, the risk classes it newly admits, the human-oversight implications (S3/S4 need a human under Law 6 and Art. V), and the assurance tier required (SOA §4).
3. **Record it in `governance/decisions/`.** Constitution Art. VI and Operational Manual §8.1 both require this, and §8.1 requires it for AIA-R2+ assurance sign-off in particular. **This directory does not exist in the repo yet**, and there is no naming or format convention. Ask the user how they want decisions recorded before creating it.
4. **Get sign-off from the user**, as founder under the interim structure. Until they approve, change nothing.
5. **Only after approval,** apply it by the recorded mechanism: the seed `_POLICIES` in Governance, a catalogue entry in `connectors/catalogue.json`, or `setMaxRiskLevel` on a deployed `AEPXPolicyRegistry` (live-chain mode). Keep the change to the approved scope, and update the tests and docs that assert the old value.

Protocol-level changes (new envelope fields, new check semantics) go through an RFC instead. See `aepx-rfcs-conformance`.

## Related skills

- `aepx-svc-governance` — the Governance service code
- `aepx-connector-bus` — where trust, policy and circuit gates run
- `aepx-blockchain` — ledger anchoring and the on-chain policy registry
- `aepx-rfcs-conformance` — RFC process and the `governance.*` conformance checks
- `aepx-architecture` — which layer enforces which Law
