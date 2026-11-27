# Release manifest — aav-v0.1.2 (DLV-15)

- Tag: `aav-v0.1.2` (GitHub release, aliabdalla-maker/aepx-core), built by `.github/workflows/agentic-antivirus.yml`
- Source: `master` after merging `feat/aav-r1-closeout-r2`
- Versions: desktop 0.1.2, endpoint agent 0.1.2, control-plane API 0.1.2 (`/health` reports version, build SHA, environment)
- Signing: unsigned beta unless the signing secrets are set (B-02); verify every download against `SHA256SUMS.txt`
- Release approver: Ali (D-02); production approval recorded on the deploy run (RA-10, `docs/APPROVALS.md`)

Asset hashes are written by the release job into `SHA256SUMS.txt`; copy them here after the release is published
(`python tools/smoke_release.py --version 0.1.2 --tag aav-v0.1.2 --all-assets --skip-api --evidence smoke.json`).

## What changed since 0.1.1

Fixes (P0/P1 from the 0.1.1 known-issues list, RA-01):
- Console menu clickable again; "This computer" panel on the dashboard (PR #431)
- Desktop app opens reliably on every OS, protects and scans this computer; agent bundled in the installers
- In-app scan works; empty `device_ids` scans every active device in the tenant (was 422)
- Baseline detection bundle published on install, so fresh deployments are never "none published" (FN-06)
- Google sign-in: redirect mode, OIDC callback endpoint, in-app popup on desktop
- SMTP relays greeted with the public host name; mail via IP-trusted relay

Security and operations:
- Edge `Strict-Transport-Security` and `Permissions-Policy` (audit M-1)
- CI code-signing hooks (Azure Artifact Signing, Apple notarisation) — active once secrets exist
- Post-deploy smoke test and approval record on every production deployment
- FastAPI lifespan handlers replace deprecated `on_event` (audit L-3)

Features carried in this release:
- Governed response harness, assistant with files, folders, images and camera (§3C/§3D)
- LLM agents (opt-in, off by default per D-07), 100-language pipeline, security dashboard, recovery workflow

## Acceptance

| Check | Command | Result |
|---|---|---|
| Control-plane tests | `pytest control-plane/tests` | recorded by CI |
| Post-deploy smoke | `tools/smoke_release.py --version 0.1.2 --build <sha>` | recorded on the deploy run |
| Release assets | `tools/smoke_release.py --tag aav-v0.1.2 --all-assets --skip-api` | after publication |
| Desktop EICAR smoke (Windows, macOS, Linux) | install, "Scan this computer" with the EICAR test file | manual, per `docs/RUNBOOKS.md` |
