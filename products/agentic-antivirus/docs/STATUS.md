# Agentic Antivirus — feature status and traceability

Status scale (S2 step 13): **planned** · **implemented** (code exists, no automated test) · **tested** (automated test passes) ·
**staging-verified** · **production-verified**, plus **blocked** (needs something outside this repository). Nothing in this
release is staging- or production-verified: no environment has been deployed (deployment needs approval, RA-10).

Evidence run: branch `feat/agentic-antivirus`, base aepx-core `57c40ec`, 18 Nov 2026, local PostgreSQL 16.15 + the real
`services/governance` service. Results: 83 Python tests passed (77 control plane incl. end-to-end with the real agent,
6 agent unit), 9 console unit tests, 1 desktop policy test, accessibility gate 84 page/theme/locale checks with 0 serious or
critical violations, compose guard passed. Android/iOS/desktop/agent-binary/container builds run only in GitHub Actions
(`.github/workflows/agentic-antivirus.yml`); they have **not** run yet. Requirement IDs are those of the signed-off register.

Percent complete (RA-16) is not reported: the weighted acceptance criteria (D-05, D-06) have not been agreed, so any
percentage would be invented (RA-17).

Test paths below are relative to `control-plane/tests/` unless shown otherwise.

## Update 27 Nov 2026 — R1 close-out and R2 build (branch `feat/aav-r1-closeout-r2`)

Owner decisions recorded (Ali = product owner and release approver; all proposed defaults accepted): 37 items,
`docs/APPROVALS.md`. Tests: control plane 177 passed (was 145), agent 10 passed. Register: 322/380 passed (84.7%),
23 in progress, 35 deferred — item by item in `docs/evidence/evidence-r1.json`.

New since 0.1.1, all covered by tests:
- Release: v0.1.2 versions; `/health` reports version, build and environment; `tools/smoke_release.py` post-deploy
  smoke test and release asset checksum verification; approval record on every production deploy (RA-10).
- Deployment: isolated staging stack (`deploy/compose.staging.yml`, synthetic seed) and a staging-first gate;
  cohost-aware `deploy.sh` (readiness inside the web container; the old loopback-port check could never pass on the
  shared VM) with mandatory backup and migrations; `rollback-rehearsal.sh` and `restore-rehearsal.sh` write timed
  evidence; `preflight.sh` records boot-volume encryption; ops scripts tested against PostgreSQL 16.
- R2: verified file handlers for Office, PDF, audio/video, archives (VFS-07/08); GraphQL read API and MCP server
  on the governed action path (INT-02, partial); agent memory with access-controlled retrieval (AGT-03/04);
  business KPIs (KPI-01); OCI Object Storage for off-VM encrypted backups (BE-05); OpenTelemetry traces with a
  collector overlay (BE-06); FastAPI lifespan handlers (audit L-3).

Still needs the VM, a provider, an account or a person: VM runs of staging/preflight/restore/rollback, GitHub
environment reviewer, signing certificates, store accounts, kernel-level blocking, live provider adapters,
1,000-endpoint load and DDoS exercises, translations + per-locale QA, gRPC/IMAP/SFTP/AMQP/MQTT/SQL transports.

## Update 19 Nov 2026 — sign-off assessment and Release 1 re-baseline

Tests: 126 passed, 0 failed (control plane 98, agent 6, console 17, desktop 5). Production (build 4e5c8ea) verified live:
/api/ready true, Google sign-in, email confirmation via the Workspace relay. New evidence: OBJ-03 (0 false positives on
60,001 benign files), OBJ-05 (0.136 percentage points agent CPU), THR-05/07, DDOS-02/04 monitoring, DDL-03, VOC-01..08.
Item-by-item status: `docs/evidence/evidence-r1.json`. Proposed scope change for Release 1 (needs owner approval):
`docs/REBASELINE-R1.md`. Release evidence: `docs/RELEASE-MANIFEST-0.1.1.md`, `docs/SECURITY-REPORT-R1.md`.

## Product requirements (PRD)

| ID | Status | Evidence / gap |
|---|---|---|
| AV-01 | tested (user mode); **blocked** for pre-open/pre-exec blocking | `test_endpoint_e2e.py::test_known_malware_blocked_quarantined_and_alerted` (on-demand and quick/full scans; scheduled scans delivered in the signed policy: `::test_scheduled_scans_are_delivered_in_signed_policy`). The on-access (file-watch) and on-execute (new-process scan) collectors are implemented in `agent.py` but not covered by an automated test. True blocking before open/execute needs a Windows minifilter / macOS Endpoint Security / Linux fanotify (B-01, B-04) |
| AV-02 | tested | `::test_restore_requires_admin_reason_and_clean_rescan`, `::test_manual_quarantine_then_clean_restore`; encrypted vault `agent/tests::test_vault_encrypts_and_restores_only_clean` |
| EDR-01 | tested | `::test_behaviour_detection_links_evidence` (process lineage, script, credential access, ransomware mass-modify + shadow delete); network/persistence/removable collectors in `agent.py` (persistence/network collectors: implemented, exercised only on Linux) |
| EDR-02 | tested (command path); **blocked** for real firewall change in CI | `::test_containment_isolation_preserves_management_and_releases`, `::test_duplicate_command_delivery_has_one_effect`; firewall rules generated for Linux/Windows/macOS (`agent/tests::test_isolation_rules_keep_management_path`) but never applied to a real host in tests |
| AI-01 | tested | `test_governed_actions.py::test_investigation_separates_facts_hypotheses_and_missing_evidence`, `::test_llm_output_is_validated_and_unsupported_claims_demoted` |
| AI-02 | tested | `test_governed_actions.py::test_missing_expired_changed_and_reused_approvals_denied`, `test_auth_tenancy.py::test_cross_tenant_requests_are_denied` |
| OPS-01 | tested | `test_endpoint_e2e.py::test_inventory_flags_stale_disabled_outdated`; console pages `web/app/devices`, `incidents`, `incident` |
| OPS-02 | tested | `::test_offline_enforcement_buffer_and_replay`, `::test_event_buffer_respects_size_limit`, `::test_unsigned_or_tampered_updates_rejected_and_rollback`, `::test_invalid_policy_signature_keeps_last_verified` |
| SEC-01 | tested with test-only signals | `test_threats_integrations.py::test_identity_alert_attributed_and_account_action_needs_scoped_approval`; live IdP/DNS/firewall adapters blocked (B-06) |
| SEC-02 | tested (reputation engine, reports); live URL feeds blocked | `::test_phishing_report_linked_and_escalated`, `::test_url_reputation_engine` |
| REC-01 | tested (tracking, approval); backup provider blocked | `::test_recovery_backup_and_return_to_service` (backup availability reported as unknown until a provider adapter is verified) |
| RSP-01..06 | tested | `test_governed_actions.py::test_defaults_per_prd_section5`, `::test_multi_endpoint_needs_explicit_approval_and_reports_each_device`, isolation test above (RSP-06) |
| RSP-07 | tested | approval binds action, targets digest, tenant (RLS), expiry: `::test_missing_expired_changed_and_reused_approvals_denied` |
| RSP-08 | tested | Ed25519-signed commands verified by the agent against the pinned key; tampered policy/update rejected (OPS-02 tests) |
| RSP-09, RSP-10, THR-10 | tested | `::test_prompt_injection_in_evidence_cannot_alter_policy_or_permissions`, `::test_model_outage_falls_back_to_rules` |
| ARC-01..04 | tested | as above; tamper: `test_endpoint_e2e.py::test_removable_media_and_tamper_events` |
| NFR-01 | implemented | TLS terminates at the host proxy; secrets via compose secrets; least-privilege RBAC tested; hashes-only default (`collect_file_contents` off). Encryption at rest relies on the OCI boot volume's default encryption (to verify on the VM) and the encrypted quarantine vault and backups |
| NFR-02 | **planned** | 1,000-endpoint load, reconnect-burst and backpressure tests not run (B-09); batch limit (1,000 events) and duplicate-safe replay tested |
| REL-01..05 | planned | release stages need the platforms and test corpora above |
| DDOS-01 | tested with test-only signals | `::test_ddos_asset_coverage_and_uncovered_alert`, `::test_critical_provider_alert_notifies_within_60s_and_tracks_mitigation` |
| DDOS-02, DDOS-04 | implemented (signal ingest + monitoring); exercises blocked | LB/DNS/origin categories accepted; capacity exercises need a provider (B-08) |
| DDOS-03 | tested (approval + rollback flow); provider apply blocked | `::test_traffic_policy_approval_and_honest_execution` |
| DDOS-05 | tested | suspected vs confirmed impact and prioritisation in the investigation (`::test_critical_provider_alert...`) |
| DDL-01 | tested | coverage endpoint accounts for every public endpoint with provider/owner/policy/capacity/exception |
| DDL-02 | tested | notification KPI `within_60s_ratio == 1.0` in test |
| DDL-03 | implemented | per-service objectives stored; thresholds must be set by you before exercises (D-06) |
| DDL-04 | tested | standing flag, approval for customer-impacting restrictions, rollback logged |
| THR-01..09 | tested with test-only signals (THR-01, 02, 03, 04, 08); implemented (THR-05, 06, 07, 09 ingest/rules) | categories and attribution tested; live sources blocked (B-06) |

## Platform and template requirements

| Area (IDs) | Status | Evidence / gap |
|---|---|---|
| Auth & accounts FN-01, BE-07, UI-09 | tested | `test_auth_tenancy.py` (register, verify, login, lockout, logout, reset, profile, delete, invitations, invite-only mode). OIDC/Google: implemented, needs your IdP client (no test against a real issuer) |
| Authorisation FN-02, BE-08, SET-04 | tested | `::test_roles_least_privilege`, settings sensitivity test |
| Tenancy BE-03, AX-10/12 | tested | `::test_rls_enforced_at_database_level`, `::test_cross_tenant_requests_are_denied`, `::test_msp_child_tenant_independent` |
| AEP-X AX-01..17 | tested (governance path, fail closed, limits, connector-bus contract) | `test_governed_actions.py::test_governance_outage_fails_closed`; AX-11 USD 1.00/task enforced in `tools/self_correct.py`; the investigation's LLM path through the bus is tested with a recorded transport only |
| Baseline data FN-03..09 | tested | CRUD, validation, pagination, exports across routers; simulation labelling FN-07 |
| Dashboards KPI-01..08, DSH-01..07 | tested (live queries, exports CSV/JSON/PDF) | `test_platform.py::test_kpis_live_and_exports`. Business KPIs (activation, conversion, retention) are **planned**: no product analytics events yet |
| Localisation L10N-01..13 | tested (catalogue, RTL, ICU plurals, fallback, locale search); translations **planned** | 1/100 locales translated: `docs/matrices/locale-coverage.md` |
| Voice VOC-01..10 | implemented | `web/lib/voice.ts`, `components/ui.tsx`; capability mapping unit-tested; no device verification: `docs/matrices/voice-coverage.md` |
| File manager VFS-01..17 | tested | `test_files.py` (8 tests incl. traversal, symlinks, quota, malware, versions, retention); office/media handlers planned: `docs/matrices/file-handlers.md` |
| Settings SET-01..06 | tested | `test_platform.py::test_settings_schema_validation_rbac_history_rollback` |
| Integrations INT-01..11 | tested (registry, egress/SSRF, maturity gate) | 14 protocols are recorded as configuration; only webhook ingest is implemented as a transport. GraphQL/gRPC/SMTP/IMAP/SFTP/AMQP/MQTT/SQL clients: **planned** |
| UI UI-01..10 | tested (build, a11y gate) | 23 routes; themes light/dark/high contrast; RTL; responsive to 390 px. TV layout not requested |
| Licensing / ads (owner, 18 Nov) | tested | `test_billing_ads.py` (10 tests): 30-day trial, ad rate 1.0/0.05, per-user and per-device, all three post-trial policies, all 11 AdMob unit IDs and both app IDs present and fail-closed, Play receipt verification. App Store and web checkout: blocked |
| Android client | implemented, not built | `clients/android`; unit tests written (`AdPolicyTest.kt`) but not run (no Android SDK here). CI job `android` |
| iOS / iPadOS client | implemented, not built; **blocked** for signing | `clients/ios`; CI simulator build only (B-03) |
| Desktop console Windows/macOS/Linux | implemented, policy tested | `clients/desktop`; installers built by CI, unsigned unless the CSC secrets exist (B-02) |
| Endpoint agent binaries | tested on Linux x64 here | PyInstaller binary built and exercised (enrol, scan, quarantine, flush) on linux-x64; the other five targets are CI matrix only |
| CI/CD CI-01..15 | implemented | workflow written and YAML-validated; **not yet run on GitHub** |
| OCI OCI-01..16 | implemented (plan, preflight, guard, backup, restore rehearsal, deploy with rollback) | preflight not run against your tenancy; nothing provisioned |
| Self-correction SC-01..12 | tested | `test_self_correct.py` (attempt limit, budget, recursion guard, redaction, verified learning, no merge path) |
| Release acceptance RA-01..17 | not passed | see blockers; no release candidate exists |

## Blockers (from register §21) and the next step for each

| ID | Next step |
|---|---|
| B-01 | Decide D-10; for Windows: WDK minifilter + EV certificate + Microsoft attestation signing |
| B-02 | Confirm `AEPX_WIN_CSC_*`, `AEPX_MAC_CSC_*`, `AEPX_APPLE_*` repository secrets exist; re-run the `desktop` job |
| B-03 | Apple Developer account; configure App Store Server API keys; implement `/v1/billing/app-store/verify` against them |
| B-04 | Request Apple's Endpoint Security entitlement for the macOS agent |
| B-05 | Confirm which supplied AdMob app ID is linked to `com.equalitysoftware.agenticantivirus`; create the Play subscription `aav_protection_monthly` at £4.99; set unit formats/placements in `monetization/ads-config.json`; set `enabled: true` |
| B-06 | Name the providers (D-03); for each, add an adapter to `VERIFIED_ADAPTERS` with a sandbox contract test |
| B-07 | Supply the compartment OCID; run `deploy/preflight.sh` in OCI Cloud Shell; approve the plan in `docs/OCI-PLAN.md` |
| B-08, B-09 | Agree exercise windows with the DDoS provider; load-test plan for 1,000 endpoints |
| B-10 | Website access to publish `/apps/agentic-antivirus`; the repo already contains the same `app-ads.txt` line for softwareequality.com (`platform/saas-ide/distribution/website`), not verified live |
| Web AdSense | Create web ad slots (10-digit IDs) in AdSense; none were supplied (the supplied IDs are AdMob units) |
| Web payments | Choose a web payment provider (Stripe or similar) for £4.99/month outside the app stores |
