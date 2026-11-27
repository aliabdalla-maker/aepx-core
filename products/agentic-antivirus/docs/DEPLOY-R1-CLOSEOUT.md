# Deploy runbook — R1 close-out and R2 build (v0.1.2)

Owner and release approver: **Ali**. Branch: `feat/aav-r1-closeout-r2` (7 commits on top of `master` `97c4746`).
Every step names the requirement IDs it closes. Commands assume a checkout of `aliabdalla-maker/aepx-core`.

## 0. Land the branch (≈10 min)

```bash
# from the git bundle delivered with this runbook
git fetch /path/to/aav-r1-closeout-r2.bundle feat/aav-r1-closeout-r2:feat/aav-r1-closeout-r2
git push origin feat/aav-r1-closeout-r2
gh pr create --base master --head feat/aav-r1-closeout-r2 \
  --title "AAV: R1 close-out (decisions, v0.1.2, staging, rehearsals) and R2 software items"
```
Alternative: `git am aav-patches/*.patch` on a branch from `master`. Wait for the `agentic-antivirus` workflow to pass
(backend tests, console, compose guard for all overlays, agent, desktop builds), then merge.

## 1. GitHub settings (≈5 min) — CI-11, RA-10

Settings → Environments:
- `staging`: no reviewers.
- `production`: **Required reviewers: Ali**; deployment branches: `master` only.
Secrets `OCI_HOST`, `OCI_USER`, `OCI_SSH_PRIVATE_KEY` must already exist (used by the deploy jobs).

## 2. One-time VM setup (≈15 min, SSH to the ai4business VM)

```bash
cd /opt/aepx-core && git fetch && git checkout <merged master sha>
sudo install -d -m 700 /etc/aav /var/lib/aav/evidence
# production: shared-VM layout, mandatory backup passphrase, platform operator for business KPIs
sudo sh -c 'openssl rand -base64 48 > /etc/aav/backup.pass && chmod 600 /etc/aav/backup.pass'
sudo tee -a /etc/aav/aav.env >/dev/null <<'EOF'
AAV_COMPOSE_FILES=compose.yml:compose.cohost.yml
AAV_BACKUP_PASSPHRASE_FILE=/etc/aav/backup.pass
AAV_PLATFORM_OPERATORS=<your sign-in email>
EOF
# staging: its own passwords and signing key; no mail, LLM or store credentials
sudo openssl genpkey -algorithm ed25519 -out /etc/aav/staging_signing_key.pem
sudo chown 10001 /etc/aav/staging_signing_key.pem && sudo chmod 400 /etc/aav/staging_signing_key.pem
sudo sh -c 'umask 077; cat > /etc/aav/aav-staging.env <<EOF
AAV_POSTGRES_PASSWORD=$(openssl rand -hex 24)
AAV_APP_DB_PASSWORD=$(openssl rand -hex 24)
AAV_SIGNING_KEY_PATH=/etc/aav/staging_signing_key.pem
AAV_BACKUP_PASSPHRASE_FILE=/etc/aav/backup.pass
EOF'
```
Keep a copy of `/etc/aav/backup.pass` in your password manager: without it no backup can be restored.

Optional now, or later:
- **Off-VM backups (BE-05):** OCI Console → Object Storage → create private bucket `aav-backups` with a lifecycle rule
  (delete after 30 days); Identity → your user → Customer Secret Keys → generate. Add to `/etc/aav/aav.env`:
  `AAV_OBJECT_STORE_ENDPOINT=https://<namespace>.compat.objectstorage.uk-london-1.oraclecloud.com`,
  `AAV_OBJECT_STORE_REGION=uk-london-1`, `AAV_OBJECT_STORE_BUCKET=aav-backups`, `AAV_OBJECT_STORE_ACCESS_KEY=…`,
  `AAV_OBJECT_STORE_SECRET_KEY=…`, and append `<namespace>.compat.objectstorage.uk-london-1.oraclecloud.com` to
  `AAV_EGRESS_ALLOWLIST`.
- **Traces (BE-06):** append `:compose.otel.yml` to `AAV_COMPOSE_FILES` (adds a 96 MB collector; traces kept 7 days).

## 3. Preflight (read-only) — OCI-03, OCI-04, RA-09, DLV-09, NFR-01

In OCI Cloud Shell (or anywhere with an authenticated OCI CLI and this repo):
```bash
AAV_COMPARTMENT_OCID=<compartment of the ai4business VM> AAV_INSTANCE_OCID=<VM OCID> \
AAV_EVIDENCE_DIR=. products/agentic-antivirus/deploy/preflight.sh
```
Pass = `PREFLIGHT PASSED` and line 8/8 shows the boot volume is encrypted at rest. Keep `preflight-*.log`.

## 4. Staging deploy and acceptance — OCI-16, RA-13, DEL-05

Actions → agentic-antivirus → Run workflow: `deploy_sha=<merged master sha>`, `target=staging`.
The job deploys the isolated staging stack (own containers, volumes, secrets; loopback port 18481) and seeds synthetic
data. Then from your machine:
```bash
ssh -L 18481:127.0.0.1:18481 <user>@<vm>        # leave open
python3 products/agentic-antivirus/tools/smoke_release.py --api http://127.0.0.1:18481/api \
  --version 0.1.2 --build <sha> --evidence smoke-staging.json
```

## 5. Rehearsals on staging — OCI-10, OCI-12, CI-15, RA-12

On the VM:
```bash
cd /opt/aepx-core/products/agentic-antivirus/deploy
COMPOSE_PROJECT_NAME=agentic-antivirus-staging COMPOSE_FILE=compose.yml:compose.staging.yml \
  AAV_BACKUP_DIR=/var/backups/aav-staging AAV_BACKUP_PASSPHRASE_FILE=/etc/aav/backup.pass ./backup.sh
AAV_BACKUP_PASSPHRASE_FILE=/etc/aav/backup.pass ./restore-rehearsal.sh /var/backups/aav-staging/<latest>.dump.enc
./rollback-rehearsal.sh <merged master sha> 4e5c8ea9ed78ed5574a99cc2c30745f54c77e86c staging
```
Pass = both print `passed`; evidence JSON in `/var/lib/aav/evidence/` (restore seconds, row counts, rollback and
roll-forward seconds, unavailable seconds).

## 6. Production deploy — AV-01, FN-06, RA-01, REL-01, RA-10

Run workflow again with `target=production`. GitHub asks you to approve (that approval is the release record). The
job takes an encrypted backup, migrates, deploys, checks readiness inside the stack, runs the public smoke test and
uploads `aav-deploy-evidence-<sha>`. A failed check rolls back to the previous verified SHA automatically.
Afterwards: `docker compose -p agentic-antivirus-staging stop` on the VM to free staging's memory.

## 7. Release v0.1.2 — REL-01, DLV-15

```bash
git tag aav-v0.1.2 <merged master sha> && git push origin aav-v0.1.2
# when the release job has finished:
python3 products/agentic-antivirus/tools/smoke_release.py --version 0.1.2 --tag aav-v0.1.2 --all-assets --skip-api \
  --evidence smoke-release-0.1.2.json
```
Copy the asset hashes into `docs/RELEASE-MANIFEST-0.1.2.md`. Update the download page links to 0.1.2.

## 8. Desktop smoke (manual, ≈20 min) — AV-01, RA-03

On one Windows, one macOS and one Linux machine: install the 0.1.2 app, sign in, **Protect this computer**, put an
EICAR test file in Downloads and run **Scan this computer**. Pass = file quarantined and an alert in the console.

## 9. Record the evidence

Commit the evidence files (`preflight-*.log`, `restore-*.json`, `rollback-*.json`, `smoke-*.json`) under
`docs/evidence/2026-11-r1/` and update `docs/evidence/evidence-r1.json` for: OCI-03, OCI-04, OCI-10, OCI-12, OCI-16,
CI-11, CI-15, RA-01, RA-09, RA-10, RA-12, RA-13, DEL-05, DLV-09, NFR-01, AV-01, FN-06, REL-01 (and BE-05 once the
bucket has a stored backup). Then fill the release row in `docs/APPROVALS.md`.

## Still with you (not code)

| Item | What is needed | Closes |
|---|---|---|
| Code signing | Azure Artifact Signing account (Windows) + Apple Developer ID; add the secrets named in the desktop job | B-02, DST-08, CI-10, RA-07, DLV-11 |
| Stores | Play Console app + service account; App Store Connect app | B-03, B-05, PRJ-21, DST-02/03/09, OBJ-08, DLV-12, PLT-03, UI-02/08/10 |
| Kernel blocking | EV certificate + Microsoft attestation signing; Apple Endpoint Security entitlement | B-01, B-04 |
| Live providers | Provider accounts (IdP, DNS, CDN/WAF, backup, URL feeds) | B-06, then DDoS/load B-08/B-09, NFR-02, DDOS-02/04, DDL-03 |
| Translations | Run `agentic-antivirus-i18n.yml` with a translation provider key; per-locale QA | L10N-01/10/11 |
