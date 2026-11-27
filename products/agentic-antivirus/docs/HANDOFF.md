# Agentic Antivirus — handoff (27 Nov 2026)

Owner and release approver: **Ali**. This note is the single place to resume from.

## 1. Where things stand

- **Code:** branch `feat/aav-r1-closeout-r2`, 18 commits on top of `master` `97c4746`. Not pushed yet. It is
  delivered as `aav-r1-closeout-r2.bundle` and `aav-patches.zip`.
- **Production:** still runs build `240774d9e933` (before this branch). None of the work below is live until
  runbook steps 0–6 are done.
- **Tests:** control plane 206 passed, agent 16, web 22 (tsc clean), distribution 14.
- **Evidence register** (`docs/evidence/evidence-r1.json`, 380 items): **322 passed (84.7%) · 30 in progress · 28 deferred**.

## 2. What the branch adds

| Area | What | Requirement IDs |
|---|---|---|
| Release ops | v0.1.2, `/health` with version and build, staging stack, staging-first and backup-first `deploy.sh`, rollback and restore rehearsals, smoke test, approval record | REL-01, OCI-10/12/16, RA-10/12/13 |
| Real-time blocking | Linux fanotify (tested for real), Windows minifilter, macOS Endpoint Security; all fail open | B-01, B-04 |
| Live providers | Google Workspace, Entra ID, Cloudflare, OPNsense, S3, URLhaus, Safe Browsing; encrypted write-only credentials; 24 h credential check before going live | B-06 |
| Transports | gRPC, SQL, IMAP, MQTT, AMQP, SFTP pull; Slack, Teams, HubSpot and ServiceNow outbound | INT-02, INT-03 |
| R2 platform | File handlers, GraphQL and MCP, agent memory, business KPIs, object storage, OpenTelemetry | R2 items |
| Languages | All 99 locales machine-translated, QA 0 errors, marked machine-translated in the console | L10N-01 |
| Audit fixes (27 Nov screenshots) | Readable validation errors, KPI no-data states, empty tables, server validation for settings, integrations, DDoS endpoints, policy hosts and cron; migration 008 scrubs a pasted key | UI, FN |
| Website | 0.1.2 page with the new capabilities; zip in `website/dist/` | DLV-15 |
| Android | `aav-android-release.yml`: signed AAB, then a Play internal-track draft; `play_upload.py --package` | B-03, DST-02 |

## 3. Do these first (security)

The 27 Nov console screenshots show three live secrets, and they must be treated as exposed:

1. Revoke the **OpenRouter key** (starts `sk-or-v1-ae55…`) in OpenRouter.
2. Create a new key and save it with `PUT /integrations/{id}/secret`. Never paste a key into the reference field.
3. Rotate the **webhook secret** on that integration.
4. Rotate the **device enrolment token**.

## 4. How to land and deploy

Follow `docs/DEPLOY-R1-CLOSEOUT.md`, steps 0–14, in order:

- 0: land the branch.
- 1: GitHub settings.
- 2: one-time VM setup.
- 3: preflight.
- 4: staging.
- 5: rehearsals.
- 6: production.
- 7: release.
- 8: desktop smoke.
- 9: evidence.
- 10: kernel blocking.
- 11: providers.
- 12: transports.
- 13: website upload.
- 14: Android AAB to Play.

## 5. Open items

**In progress (30). The code is done; each needs a run, an account or a review by you:**

- **Deploy, staging and rehearsal runs:** DEL-05, AV-01, NFR-01, REL-01, FN-06, CI-11, CI-15, OCI-03/04/10/12/16, RA-01/02/03/09/10/12/13, DLV-01, DLV-09, BE-05.
- **Native review of the 99 locales** (`tools/i18n_review.py`): L10N-01/10/11.
- **Pick the vendor products** (an ERP choice is still open): INT-02, INT-03.
- **Kernel signing** (Microsoft attestation, Apple ES entitlement): B-01, B-04.
- **Provider accounts and keys:** B-06.

**Deferred (28). These need something outside the code:**

- **Code signing:** B-02, DST-08, CI-10, RA-07, DLV-11.
- **Store listings and uploads:** B-03, B-05, PRJ-21, DST-02/03/09, OBJ-08, DLV-12, PLT-03, UI-02/08/10.
- **Live DDoS and load tests on real providers:** B-08, B-09, NFR-02, DDOS-02/04, DDL-03.
- **Later release stages and optional platforms** (roadmap): REL-02…05, PLT-04.

## 6. What could not be done from the build session

- **Push to GitHub.** No credentials are available there.
- **Upload to www.softwareequality.com.** The host is blocked from the session. Upload the website zip (step 13).
- **Build and upload the AAB.** The Android SDK and Play credentials are not available there. Run `aav-android-release.yml` (step 14).
- **Machine translation with local models.** Hugging Face was blocked, so translations came from the built-in file engine and need native review.

## 7. How to resume

```bash
git fetch aav-r1-closeout-r2.bundle feat/aav-r1-closeout-r2:feat/aav-r1-closeout-r2 && git checkout feat/aav-r1-closeout-r2
cd products/agentic-antivirus/control-plane && pip install -r requirements.txt && pytest -q   # needs PostgreSQL 16
cd ../web && npm ci && npx tsc --noEmit && npx vitest run
python3 ../website/build_site.py
```
Key files:

- `docs/STATUS.md`
- `docs/evidence/evidence-r1.json`
- `docs/APPROVALS.md`
- `docs/RELEASE-MANIFEST-0.1.2.md`
- `docs/matrices/translation-qa.md`
