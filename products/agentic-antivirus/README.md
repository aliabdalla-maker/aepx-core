# Agentic Antivirus and Cybersecurity Protection Platform

The platform provides endpoint antivirus, EDR, DDoS and availability monitoring, and governed AI investigation, built on AEP-X (`services/governance`; the connector bus for the optional model). It implements the signed-off requirements register of 18 Nov 2026. Nothing here is deployed or published. What is tested and what is blocked is in [docs/STATUS.md](docs/STATUS.md).

| Path | What |
|---|---|
| `control-plane/` | FastAPI API (104 paths, OpenAPI at `/v1/openapi.json`), PostgreSQL schema with RLS, integration tests |
| `agent/` | User-mode endpoint agent, packaging (PyInstaller, systemd, launchd, Windows service) |
| `detection/` | Shared detection engine and the signed baseline rule bundle |
| `web/` | Accessible console (Next.js static export, PWA, 100-locale catalogue, read-aloud and dictation, AdSense gating) |
| `clients/` | Android (AdMob + Play Billing), iOS/iPadOS (AdMob), desktop (Electron) shells around the console |
| `monetization/` | AdMob/AdSense identifiers, pricing (£4.99/month, 30-day trial, 95% fewer ads when paid), `app-ads.txt` |
| `deploy/` | OCI Always Free compose, guard, read-only preflight, backup, restore rehearsal, deploy with rollback |
| `tools/` | Bounded self-correction loop, matrix generator, CI harness |
| `docs/` | Status and traceability, architecture and threat model, runbooks, coverage matrices |

## Run the tests

```bash
# PostgreSQL 16 superuser DSN for a scratch server
export AAV_TEST_PG_ADMIN_DSN=postgresql://postgres:pw@127.0.0.1:5432/postgres
pip install -r control-plane/requirements.txt -r ../../services/governance/requirements.txt -r agent/requirements.txt pytest
cd control-plane && python -m pytest tests ../agent/tests
cd ../web && npm ci && npx vitest run && npx next build
```

The control-plane tests start the real AEP-X governance service from `services/governance`. They create a temporary database and drop it afterwards.
