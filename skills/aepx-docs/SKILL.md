---
name: aepx-docs
description: Map of aepx-core's docs/ — reading order and purpose of each document, which doc to update for which change, how the .md/.html/.pdf versions relate (and when to ask before regenerating), plus Monetization-Strategy and Operational-Manual pointers. Use when looking up or updating AEP-X documentation.
---

# AEP-X documentation (`docs/`)

## Reading order and purpose (from README.md)

| # | Document | Formats in repo | Purpose |
|---|---|---|---|
| 1 | ADLC-Plan | .md .html .pdf | The reconciled development lifecycle. Every scope decision traces back to its **Critical Evaluation (§15)**. |
| 2 | Handoff | .html only | Committed Year-1 scope and blockers |
| 3 | Instructional-Manual | .html .pdf | The step-by-step build runbook for registry, identity, trust, memory, cache and gateway |
| 4 | Microservices-Implementation-Guide | .html .pdf | Adds discovery, workflow, safety and governance (Tier 2, Kafka choreography) |
| 5 | SOA-Architecture | .md .html .pdf | The Universal Connector Layer (`connector-bus/` + `connectors/`); risk taxonomies (§1.1); security and assurance (§4); build order (§5) |
| 6 | Microservices-Architecture-v2 | .md .html .pdf | Adds knowledge, verification, cost-optimiser, ml-integration and the L0–L5 cache |
| 7 | Hybrid-Architecture-and-Comparison | .md .html .pdf | Why the platform uses a microservices core plus an SOA integration layer |
| 8 | Operational-Manual | .html .pdf | Running, verifying and troubleshooting the live stack. UML use-case and sequence diagrams |
| 9 | Connector-Catalogue | .md only | All 107 connectors by category, with risk class and maturity. **Generated from `connectors/catalogue.json`.** |
| 10 | Console-and-Bridge | .md only | The AEP-X Console (:8083), the RFC-0008 bridge, Billing, live-chain (anvil) mode, and the SDK plugin list |
| 11 | Monetization-Strategy | .md only | The open-core + governed-infrastructure model: five revenue lines, indicative pricing, sequencing |

Also relevant outside `docs/`:
- `README.md`: repository layout and service counts.
- `rfcs/`: protocol specifications.
- `governance/`: the constitution and the Laws.
- `governance/contracts/README.md`: contract env vars.
- `attachment/AEP-X Ultra v2 (source).docx`: the original source, kept for traceability.

## Operational-Manual pointers

Sections:
1. System Overview
2. UML Use Case
3. Sequence diagrams: 3.1 bus mediation (Laws 2 and 8), 3.2 workflow and Kafka choreography, 3.3 cache-first routing (Law 5)
4. Runbook: 4.1 start/stop (including `docker compose down -v` to re-run `schemas/sql`), 4.2 port map, 4.3 health verification
5. Smoke Test Procedure (six curl steps with pass criteria)
6. Troubleshooting (disk-full builds, pgvector, the Kafka consumer race, KRaft CLUSTER_ID, 403 trust and policy denials, `connector_count: 0`, and more)
7. Backup & Restore
8. Connector Operations: 8.1 promote a stub, 8.2 add a connector, 8.3 and 8.4 "do not bypass" the trust, policy and circuit gates
9. Definition of Done

It exists only as HTML and PDF. Its port map lists neither oracle-bridge, marketplace, billing nor aepx-console, and it counts "16 services" at the gateway. Treat it as partially stale against `docker-compose.yml`.

## Monetization-Strategy pointers

- **Revenue lines:** (1) Open-core licensing, (2) Managed cloud, (3) Marketplace take-rate, (4) Certification & training, (5) Blockchain / bridge lines (RFC-0008).
- **Other sections:** indicative pricing; sequencing mapped to funding stages; payment processing via `services/billing` (Stripe Checkout, key from `STRIPE_API_KEY` only, no card data touches AEP-X); and "the honest caveat" (adoption is the binding risk, so Enterprise Edition and certification come first).
- Pricing and sequencing are business decisions. Do not edit them without the user.

## Which doc to update for which change

| Change | Update |
|---|---|
| New or renamed service, or a port change | `README.md` layout, Operational-Manual §4.2 port map, the `aepx-run-stack` skill's port table (then cut a plugin release), and the relevant architecture doc |
| New connector, or a stub promoted | `connectors/catalogue.json`, then `python scripts/gen_connector_catalogue.py` to regenerate `Connector-Catalogue.md` (CI's `catalogue` job fails if you forget). `schemas/sql/003_connectors.sql` has no generator; ask the user before hand-editing it |
| Protocol behaviour (envelope, trust, policy, checks) | a new or updated RFC in `rfcs/`, and RFC-0007 §4.2 for a new conformance check |
| Console, bridge, billing or live-chain operation | `Console-and-Bridge.md` |
| Contract or chain env vars | `governance/contracts/README.md`, RFC-0006 and RFC-0008 |
| Laws, constitution or policy ceiling | `governance/*.md`, only via an approved governance decision (see `aepx-governance-policy`) |
| Runbook, troubleshooting or smoke steps | Operational-Manual |
| Pricing and business model | Monetization-Strategy (user-owned) |
| Scope decisions | ADLC-Plan §15 is the reference; do not rewrite it casually |

## How .md, .html and .pdf relate

The facts below come from inspecting the files:
- Four documents have all three formats: ADLC-Plan, SOA-Architecture, Microservices-Architecture-v2 and Hybrid-Architecture-and-Comparison.
- Handoff, Instructional-Manual, Microservices-Implementation-Guide and Operational-Manual have **no .md source**, so the .html is the source.
- The .html files are hand-styled standalone pages with inline CSS and no generator meta tag.
- The PDFs' metadata shows they were printed from Chrome (`Creator: HeadlessChrome`, `Producer: Skia/PDF`).
- The repo has **no build script, Makefile or CI step** that turns .md into .html or .html into .pdf.

It is therefore **unclear** whether the .html files are generated from the .md files or maintained separately, and how the PDFs are produced exactly. **Ask the user before regenerating or hand-editing any .html or .pdf.** When you change a .md that has an .html/.pdf sibling, tell the user those siblings are now out of date rather than silently regenerating them. README links point at the .html versions for most documents.

## Related skills

- `aepx-architecture` — the platform map these docs describe
- `aepx-rfcs-conformance` — RFC format and process
- `aepx-governance-policy` — constitution and Laws
- `aepx-new-service` — doc touch-points for a new service
- `aepx-connector-adapter` — connector catalogue changes
