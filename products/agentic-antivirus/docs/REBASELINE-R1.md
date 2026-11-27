# Release 1 re-baseline proposal (19 Nov 2026)

Status: **decisions approved 27 Nov 2026 by Ali (product owner and release approver, D-02)** — every item under *Accept proposed decision* is accepted as written and recorded in `docs/evidence/evidence-r1.json` (verification level `owner-decided`; see `docs/APPROVALS.md`). The *Defer to R2* list is scope guidance: R2 items are being built on `feat/aav-r1-closeout-r2`.

Register items: 380. Met with evidence: 279. Proposed deferrals to Release 2: 43. Proposed decision defaults: 34. Remaining work: 24.

Release 1 scope after deferral: 337 items; met now 279 (82.8%); met once the proposed decisions are approved 313 (92.9%). The remaining items reach 100% only through the actions listed under Remaining work.

## Release 1 test corpus (DLV-22)

- Positive control: EICAR test string, plain and embedded (test_endpoint_e2e.py).
- Benign corpus: 60,001 OS-installed files (4.3 GB, Linux) scanned 19 Nov 2026 — 0 false positives; plus 5,500 files per CI run (test_register_r1.py).
- Behaviour scenarios: encoded PowerShell from Office, LSASS dump via comsvcs.dll, ransomware mass-modify + shadow-copy delete.

## Platform coverage (DLV-24)

| Platform | Release 1 | Notes |
|---|---|---|
| Web console | yes | live |
| Windows x64/arm64 desktop + agent | yes (unsigned beta) | user-mode protection |
| macOS arm64/x64 desktop + agent | yes (ad-hoc signed beta) | user-mode protection |
| Linux x64/arm64 AppImage/deb + agent | yes | user-mode protection |
| Docker/GHCR control plane | yes | :latest, :edge |
| Android, iOS/iPadOS | Release 2 | store publication |

## Defer to R2

| ID | Item | Proposal | Who |
|---|---|---|---|
| PRJ-21 | Google Play | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| OBJ-08 | Publication | R1 publication channels = website, GitHub release, Docker/GHCR; stores in R2 | you (approve) |
| NFR-02 | Reliability and scale | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |
| REL-02 | 2. Managed | Later release stages / optional platforms are R2+ by definition | you (approve) |
| REL-03 | 3. Agentic | Later release stages / optional platforms are R2+ by definition | you (approve) |
| REL-04 | 4. Expanded | Later release stages / optional platforms are R2+ by definition | you (approve) |
| REL-05 | Release | Later release stages / optional platforms are R2+ by definition | you (approve) |
| DDOS-02 | Protocol exhaustion | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |
| DDOS-04 | DNS and origin | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |
| DDL-03 | Service continuity | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |
| UI-02 | Mobile: Android Kotlin/Compose or verified | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| UI-08 | Icon assets: SVG, adaptive Android icons, iOS app | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| UI-10 | Cross-platform UI | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| BE-05 | Object storage: verified OCI Always Free-eligible | Object storage, OTel collector, RAG memory, business-KPI analytics move to R2 | you (approve) |
| BE-06 | Telemetry: OpenTelemetry where feasible | Object storage, OTel collector, RAG memory, business-KPI analytics move to R2 | you (approve) |
| L10N-01 | 100 selectable locales from the catalogue below (a | R1 ships English with the 100-locale catalogue and fallback; translations + per-locale QA move to R2 (D-11) | you (approve) |
| L10N-10 | Locale-specific accessibility | R1 ships English with the 100-locale catalogue and fallback; translations + per-locale QA move to R2 (D-11) | you (approve) |
| L10N-11 | Per-locale QA required; each locale individually | R1 ships English with the 100-locale catalogue and fallback; translations + per-locale QA move to R2 (D-11) | you (approve) |
| VFS-07 | Preview/edit/convert capability-gated behind a | Office/media file handlers and non-REST transports move to R2 | you (approve) |
| VFS-08 | Format handlers required: text, CSV, JSON, XML, | Office/media file handlers and non-REST transports move to R2 | you (approve) |
| INT-02 | Protocols: REST, OpenAPI, GraphQL, gRPC, MCP, | Office/media file handlers and non-REST transports move to R2 | you (approve) |
| INT-03 | Ecosystems: in-house, existing enterprise, cloud, | Office/media file handlers and non-REST transports move to R2 | you (approve) |
| KPI-01 | Business | Object storage, OTel collector, RAG memory, business-KPI analytics move to R2 | you (approve) |
| PLT-03 | Mobile | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| PLT-04 | Optional | Later release stages / optional platforms are R2+ by definition | you (approve) |
| DST-02 | Android | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| DST-03 | iOS | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| DST-08 | Signing keys | Code-signed installers move to R2; R1 ships as an unsigned beta with published SHA-256 sums | you (approve) |
| DST-09 | Publication | R1 publication channels = website, GitHub release, Docker/GHCR; stores in R2 | you (approve) |
| CI-10 | Signed packages when credentials are available; | Code-signed installers move to R2; R1 ships as an unsigned beta with published SHA-256 sums | you (approve) |
| AGT-03 | Memory: retrieval-augmented, source attribution, | Object storage, OTel collector, RAG memory, business-KPI analytics move to R2 | you (approve) |
| AGT-04 | Retrieval: access-controlled RAG | Object storage, OTel collector, RAG memory, business-KPI analytics move to R2 | you (approve) |
| RA-07 | Signed release artifacts and correct ownership | Code-signed installers move to R2; R1 ships as an unsigned beta with published SHA-256 sums | you (approve) |
| DLV-11 | Signed platform builds / packages where possible, | Code-signed installers move to R2; R1 ships as an unsigned beta with published SHA-256 sums | you (approve) |
| DLV-12 | Store publication checklists | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| B-01 | AV-01 scanning on access and | Kernel pre-execution blocking (Windows minifilter, macOS Endpoint Security) moves to R2; R1 is user-mode (D-10) | you (approve) |
| B-02 | Signed Windows and macOS installers | Code-signed installers move to R2; R1 ships as an unsigned beta with published SHA-256 sums | you (approve) |
| B-03 | iOS / iPadOS builds and App Store | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| B-04 | macOS endpoint telemetry and | Kernel pre-execution blocking (Windows minifilter, macOS Endpoint Security) moves to R2; R1 is user-mode (D-10) | you (approve) |
| B-05 | Android Play publication | Mobile store publication (Android/iOS) moves to R2 | you (approve) |
| B-06 | Live provider integrations | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |
| B-08 | DDoS and load exercises | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |
| B-09 | 1,000-endpoint scale validation | Live provider adapters, DDoS capacity exercises and 1,000-endpoint load test move to R2; R1 monitoring is tested | you (approve) |

## Accept proposed decision

| ID | Item | Proposal | Who |
|---|---|---|---|
| PRJ-11 | Data classification | Classify telemetry as Confidential; UK GDPR; privacy page live; no voice recording stored | you (approve) |
| PRJ-24 | Legal / privacy | Classify telemetry as Confidential; UK GDPR; privacy page live; no voice recording stored | you (approve) |
| PRJ-30 | Measurable KPI | R1 targets = PRD proposed values (OBJ-03 <0.5%, OBJ-04 30 s, OBJ-05 3 pp, DDL-02 60 s) | you (approve) |
| DEL-06 | 06 Delivery | R1 delivery channels = OCI + GitHub + Docker (stores R2) | you (approve) |
| DEL-07 | 07 Operations | Operator = product owner; critical alerts via console + email notifications | you (approve) |
| DEL-12 | A feature is complete only with an operational API | R1 corpus = EICAR + benign OS/office corpus; equal-weight acceptance criteria | you (approve) |
| DEL-18 | Report measurable progress, evidence, blockers | R1 corpus = EICAR + benign OS/office corpus; equal-weight acceptance criteria | you (approve) |
| VIS-01 | Protect against viruses, worms, trojans, | User-mode agent for R1 (scan on access/execute/download/demand + quarantine) | you (approve) |
| VIS-02 | Protect against stolen credentials, compromised | R1 accepted on tested ingest/approval flows with test signals; live feeds in R2 (D-03) | you (approve) |
| SEC-01 | Identity and network | R1 accepted on tested ingest/approval flows with test signals; live feeds in R2 (D-03) | you (approve) |
| SEC-02 | Phishing and web | R1 accepted on tested ingest/approval flows with test signals; live feeds in R2 (D-03) | you (approve) |
| REC-01 | Recovery coordination | R1 accepted on tested ingest/approval flows with test signals; live feeds in R2 (D-03) | you (approve) |
| DDOS-01 | Volumetric floods | R1 accepted on tested ingest/approval flows with test signals; live feeds in R2 (D-03) | you (approve) |
| DDOS-03 | Application-layer | R1 accepted on tested ingest/approval flows with test signals; live feeds in R2 (D-03) | you (approve) |
| AX-14 | LLM provider configurable and opt-in | No LLM provider in R1; rules-based investigation with LLM opt-in off | you (approve) |
| VOC-09 | Privacy and retention policy required for voice da | Classify telemetry as Confidential; UK GDPR; privacy page live; no voice recording stored | you (approve) |
| DSH-04 | Measurable targets defined per project (PRJ-30) | R1 targets = PRD proposed values (OBJ-03 <0.5%, OBJ-04 30 s, OBJ-05 3 pp, DDL-02 60 s) | you (approve) |
| RA-06 | Approved accessibility and security tests; no | Automated security tests (DLV-07) accepted for the R1 beta; independent penetration test before general availability | you (approve) |
| RA-16 | Percent complete = weighted passed acceptance | R1 corpus = EICAR + benign OS/office corpus; equal-weight acceptance criteria | you (approve) |
| C-03 | The templates' generic modules (self- | Template generic modules apply as implemented; translations deferred | you (approve) |
| C-04 | The locale catalogue lists both fil (Filipino) | Keep both fil and tl as listed | you (approve) |
| C-05 | OCI Always Free only, with no chargeable | No external providers in R1 (all R2) | you (approve) |
| C-07 | PRD targets are "proposed"; templates | R1 corpus = EICAR + benign OS/office corpus; equal-weight acceptance criteria | you (approve) |
| D-03 | Providers for: identity provider, DNS, firewall, | No external providers in R1 (all R2) | you (approve) |
| D-04 | Data classification and legal/privacy | Classify telemetry as Confidential; UK GDPR; privacy page live; no voice recording stored | you (approve) |
| D-05 | Test corpora and environment: must-block | R1 corpus = EICAR + benign OS/office corpus; equal-weight acceptance criteria | you (approve) |
| D-06 | Measurable KPI targets and per-service DDoS | R1 targets = PRD proposed values (OBJ-03 <0.5%, OBJ-04 30 s, OBJ-05 3 pp, DDL-02 60 s) | you (approve) |
| D-07 | LLM provider for the investigation assistant | No LLM provider in R1; rules-based investigation with LLM opt-in off | you (approve) |
| D-08 | OCI compartment OCID | Use the existing compartment that hosts the ai4business VM | you (approve) |
| D-09 | Token and cost cap for self-correction | USD 1.00 per self-correction task (S4) | you (approve) |
| D-10 | Windows endpoint agent approach: user-mode | User-mode agent for R1 (scan on access/execute/download/demand + quarantine) | you (approve) |
| D-11 | Which template generic modules apply (C-03) | Template generic modules apply as implemented; translations deferred | you (approve) |
| D-12 | Account model for a B2B tenant product: open | B2B tenants with open self-registration and invitations | you (approve) |
| D-13 | Locale catalogue fil/tl | Keep both fil and tl as listed | you (approve) |

## Remaining work

| ID | Item | Proposal | Who |
|---|---|---|---|
| PRJ-13 | Product owner | Name product owner and release approver; sign §22 | you |
| PRJ-14 | Release approval | Name product owner and release approver; sign §22 | you |
| DEL-05 | 05 Validation | Staging stack (second compose project, sanitised data) on the same Always Free VM + acceptance run | me, with your deploy approval |
| AV-01 | Malware prevention | Merge PR #431; I redeploy, publish definitions, cut aav-v0.1.2 and smoke-test the installers | you, then me |
| NFR-01 | Security and privacy | Run deploy/preflight.sh (read-only) and record shape, quotas, boot-volume encryption | me, in Cloud Shell |
| REL-01 | 1. Endpoint | Merge PR #431; I redeploy, publish definitions, cut aav-v0.1.2 and smoke-test the installers | you, then me |
| FN-06 | Production data | Merge PR #431; I redeploy, publish definitions, cut aav-v0.1.2 and smoke-test the installers | you, then me |
| CI-11 | Protected production environment; separate | Create GitHub environment 'production' with you as required reviewer | you |
| CI-15 | Rollback to the last verified immutable release | Rollback rehearsal 0.1.2 -> 0.1.1 and backup/restore rehearsal on the VM | me, with your deploy approval |
| OCI-03 | Compute preference VM.Standard.A1.Flex, arm64, | Run deploy/preflight.sh (read-only) and record shape, quotas, boot-volume encryption | me, in Cloud Shell |
| OCI-04 | Preflight: authenticate and verify region and | Run deploy/preflight.sh (read-only) and record shape, quotas, boot-volume encryption | me, in Cloud Shell |
| OCI-10 | Data backup compatible with verified free quotas; | Rollback rehearsal 0.1.2 -> 0.1.1 and backup/restore rehearsal on the VM | me, with your deploy approval |
| OCI-12 | Zero downtime best-effort only, if capacity and | Rollback rehearsal 0.1.2 -> 0.1.1 and backup/restore rehearsal on the VM | me, with your deploy approval |
| OCI-16 | Stage with sanitised data | Staging stack (second compose project, sanitised data) on the same Always Free VM + acceptance run | me, with your deploy approval |
| RA-01 | All P0 and P1 defects resolved | Merge PR #431; I redeploy, publish definitions, cut aav-v0.1.2 and smoke-test the installers | you, then me |
| RA-02 | All committed / mandatory requirements have | Met when every other R1 item is met | derived |
| RA-03 | Functional web and target-platform smoke tests | Merge PR #431; I redeploy, publish definitions, cut aav-v0.1.2 and smoke-test the installers | you, then me |
| RA-09 | Cost and resource preflight passed | Run deploy/preflight.sh (read-only) and record shape, quotas, boot-volume encryption | me, in Cloud Shell |
| RA-10 | Deployment approval recorded; human approval | Name product owner and release approver; sign §22 | you |
| RA-12 | Rollback procedure tested | Rollback rehearsal 0.1.2 -> 0.1.1 and backup/restore rehearsal on the VM | me, with your deploy approval |
| RA-13 | Staging acceptance evidence | Staging stack (second compose project, sanitised data) on the same Always Free VM + acceptance run | me, with your deploy approval |
| DLV-01 | Validated PRD and acceptance matrix; | Name product owner and release approver; sign §22 | you |
| DLV-09 | OCI Always Free preflight and deployment | Run deploy/preflight.sh (read-only) and record shape, quotas, boot-volume encryption | me, in Cloud Shell |
| D-02 | Product owner and release approval owner | Name product owner and release approver; sign §22 | you |
