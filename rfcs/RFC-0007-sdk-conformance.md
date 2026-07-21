# RFC-0007: SDK Plugin Architecture & Protocol Conformance

Status: Draft
Author(s): AEP-X Founding Team
Created: 21 July 2026

## 1. Abstract

Defines the SDK's plugin contract, the protocol conformance check catalogue, and the two developer-facing platforms that surface them: the Conformance testing platform and the Workbench utilisation platform.

## 2. Motivation

RFC-0001–0006 define what a conformant AEP-X deployment does; nothing so far defines how anyone *proves* a deployment conforms, or extends the SDK without forking it. Per ADLC Plan §15.5, the RFCs stay "living design docs until third-party implementers exist" — a runnable conformance suite is precisely what makes third-party implementation testable, and a plugin architecture is what lets those parties integrate without patching the SDK core.

## 3. Design Goals

Everything here must run against any live deployment with zero privileged access (only public service APIs), degrade cleanly when a subsystem is absent (an older deployment missing RFC-0006 endpoints skips those checks rather than failing them), and reuse one implementation everywhere — the conformance engine lives in the SDK and is surfaced unchanged by the CLI and the testing platform.

## 4. Specification

**4.1 Plugin contract.** A plugin is any object with an identifier-safe `name` and an `attach(client)` method. `AepxClient.use(plugin)` attaches it and exposes it as `client.<name>`; name collisions with client attributes are rejected. Third parties publish plugins under the **`aepx.plugins`** entry-point group; `AepxClient(discover_plugins=True)` loads them, and a plugin that fails to import is dropped silently (one broken third-party package must never break client construction). The five built-ins — `did`, `connectors`, `trust`, `ledger`, `audit` — are attached to every client at construction and are *also* published through the same entry-point group, so the discovery mechanism is dogfooded rather than special-cased.

**4.2 Conformance checks.** `aepx.conformance.CHECKS` is the normative catalogue. Each check returns PASS (behaviour observed), FAIL (deployment reachable but non-conformant), or SKIP (subsystem unreachable — a deployment state, not a verdict). The catalogue covers: RFC-0001 (envelope field set, routing through the bus's governed chain, 404 on unknown connectors), RFC-0002 (default-50 trust for fresh entities, component adjust round-trip), Governance (S0–S4 ordinal policy consistency, audit-trail shape), RFC-0006 (did:key mint→resolve round-trip, malformed-DID rejection, ledger anchor hash-chain fields, verify contract), and gateway aggregate health.

**4.3 Report.** `run_conformance(client, ids=None)` yields a report with per-check results and summary counts. A deployment is **conformant** iff zero checks fail *and* at least one passes — skips don't count against conformance, and proving nothing proves nothing.

**4.4 Platforms.** The Conformance service (`platform/conformance/`, port 8082) exposes `POST /runs` (execute against any target, in-cluster by default), `GET /runs[/{id}]` (last 50 kept in memory), `GET /checks`, and a GUI. The Workbench (`platform/workbench/`, port 8081) proxies the SDK plugins through `/api/*` endpoints with a tabbed GUI — envelope sender, DID mint/resolve/agent registration, trust inspection, ledger anchor verification, audit tail. Both build with the SDK installed from source (repo-root build context).

**4.5 CLI.** `aepx test` runs the suite (exit 0 iff conformant — CI-usable), `aepx did create|resolve`, `aepx invoke <connector> --payload`, `aepx plugins`. All accept `--gateway/--bus/--identity/--trust/--governance/--registry` target overrides.

## 5. Data Model / Schema

No persistent schema — conformance runs are deliberately ephemeral (an in-memory ring buffer); a conformance *certificate* store is out of scope until third-party implementers exist.

## 6. Security & Compliance Considerations

The conformance suite only exercises public API surface and creates only throwaway entities (random conformance-* trust entities, unregistered DIDs). The Workbench proxies whatever its deployment can reach — it is a developer tool for trusted networks, not a hardened public portal; its `/api/invoke` passes through the bus's full trust/policy/circuit gate, so it cannot reach anything the protocol itself wouldn't allow.

## 7. Backward Compatibility

`Agent` keeps its documented behaviour (now backed by `AepxClient`). Old deployments without RFC-0006 endpoints skip those checks rather than failing — the suite is usable against any protocol version to date.

## 8. Reference Implementation

`sdk/python/aepx/{client.py,plugins/,conformance/}`, `cli/aepx_cli/__main__.py`, `platform/conformance/`, `platform/workbench/`.

## 9. Open Questions

Whether conformance runs should eventually emit signed, ledger-anchored certificates (tying RFC-0006's anchoring to RFC-0007's verdicts) — deferred until a third party actually asks to prove conformance to someone else.
