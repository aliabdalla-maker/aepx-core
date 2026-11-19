# Runbooks: OCI deployment, rollback, incidents, store publication

## 1. OCI Always Free plan (not applied; needs written approval)

| Resource | Shape / size | Always Free? | Notes |
|---|---|---|---|
| 1 compute instance | VM.Standard.A1.Flex, 2 OCPU, 12 GB, Ubuntu (arm64) | yes (tenancy allowance 4 OCPU / 24 GB) | or reuse the existing approved aepx VM if it has 2 OCPU / 2 GB headroom |
| Boot volume | 50 GB | yes (200 GB total block + boot) | backups stored here, encrypted |
| Networking | existing VCN + public IP; host reverse proxy (TLS) | yes | **no** OCI load balancer, **no** paid database, **no** registry |
| Upstream DDoS/WAF | external provider (D-03) | outside OCI | chosen by you |

**Steps**
1. In OCI Cloud Shell run `AAV_COMPARTMENT_OCID=… products/agentic-antivirus/deploy/preflight.sh`. It is read-only and stops on any cost risk.
2. Record the output, then get written approval from the release approval owner (PRJ-14).
3. On the VM, create `/etc/aav/aav.env` (mode 600) containing `AAV_POSTGRES_PASSWORD`, `AAV_APP_DB_PASSWORD` (both 32+ random characters), `AAV_SIGNING_KEY_PATH=/etc/aav/signing.pem` and `AAV_BACKUP_PASSPHRASE_FILE`.
4. Generate the Ed25519 key: `openssl genpkey -algorithm ed25519 -out /etc/aav/signing.pem && chmod 600 /etc/aav/signing.pem`.
5. Add `deploy/nginx-host-location.conf` to the existing TLS server block, then run `nginx -t && systemctl reload nginx`.
6. Run the GitHub workflow `agentic-antivirus` with `deploy_sha`. The protected environment asks for approval, and the job runs `deploy/deploy.sh SHA` (guard → backup → up → readiness → automatic rollback).
7. Verify independently (RA-11): `curl https://api.softwareequality.com/apps/agentic-antivirus/api/health`. Compare the running image digest with the CI summary.
8. Publish the signed baseline detections, signed in by the operator tenant admin: `POST /v1/updates` with `detection/rules/baseline.json`.

## 2. Rollback

- **Application:** `deploy.sh` returns to `.last-verified-sha` automatically on failed readiness. To do it by hand: `git checkout <sha> && docker compose up -d --build`.
- **Detection or agent update:** propose `rollback_update` to a verified version from the console, or revoke a bad bundle with `POST /v1/updates/{kind}/{version}/revoke`. Agents keep the last verified version.
- **Database:** `deploy/restore-rehearsal.sh <backup>` proves the backup is good. Production restore is a manual, approved step: stop `control-plane`, then `pg_restore` into a new database and switch the DSN.
- **Traffic policy:** use "Roll back" on the DDoS page, which goes through the approval path.

## 3. Incident playbooks

| Situation | First 15 minutes | Then |
|---|---|---|
| Ransomware alert (`beh.ransom.*`) | Open the incident; run the investigation; approve `isolate_device` (expires, management kept); approve `terminate_process` | Verify backups (REC-01); add recovery steps; approve return to service before resolving |
| Credential theft (`beh.cred.*`, identity alerts) | Isolate the device; with an identity integration, approve `revoke_sessions` scoped to the account | Reset credentials outside the product; check other devices for the same hash or user |
| DDoS (critical provider alert) | Check DDoS status (mitigation active, affected assets); confirm standing provider mitigation is on | Propose a rate limit or challenge for the service; tenant admin approves; watch the SLOs; roll back if false positives |
| Agent tamper / protection disabled | Check the device's last heartbeat; contact the device owner | Re-enrol if the identity is lost; review local admin rights |
| AEP-X governance down | `/ready` shows `aepx_governance` not true; actions are denied (expected) | Restart the `governance` container; scanning and alerting are unaffected |
| Model outage | Investigations return rules-only findings | No action needed; optional LLM is opt-in |
| Suspected audit tampering | `GET /v1/audit/verify` shows a break | Preserve the DB snapshot; restore the rehearsal copy; investigate host access |

## 4. Store and website publication checklists (publish only after explicit approval)

**Google Play (DST-02)**
- [ ] Confirm in AdMob which app ID belongs to package `com.equalitysoftware.agenticantivirus`. Set `aav.admobAppId` and the unit formats and placements in `monetization/ads-config.json`.
- [ ] Create the subscription `aav_protection_monthly`: base plan GBP 4.99 monthly, no free-trial offer in Play (the 30-day trial is account-based on the server).
- [ ] Place the Play service account JSON on the VM and set `AAV_PLAY_SERVICE_ACCOUNT_FILE`.
- [ ] Run the CI `android` job with the upload key secrets. Compare the printed SHA-256 fingerprint with Play Console → App integrity → Upload key.
- [ ] Data safety form: device telemetry and file hashes (security), email (account), advertising ID (AdMob, with consent).
- [ ] Ads declaration: yes. Content rating questionnaire. Privacy policy URL `/apps/agentic-antivirus/privacy/`.
- [ ] Internal testing track first, then production only after approval.

**Apple App Store (DST-03)**: blocked until an Apple Developer account exists.
- [ ] Register the bundle ID, set `AEPX_APPLE_*` secrets, create the iOS AdMob app and a StoreKit subscription at £4.99.
- [ ] Implement App Store Server API verification (`/v1/billing/app-store/verify`), then archive, sign, upload to TestFlight and submit for review.

**Desktop (DST-04..07)**
- [ ] Set the `AEPX_WIN_CSC_*` and `AEPX_MAC_CSC_*` secrets and Apple notarisation credentials.
- [ ] Run the `desktop` job with channel `beta`. Check `SHA256SUMS-*`, test the installers, then re-run with `stable`.

**Website (DST-01)**
- [ ] Publish the console at `/apps/agentic-antivirus/` with release notes, licence, privacy policy, support link and system requirements, plus signed agent downloads with `SHA256SUMS`.
- [ ] Confirm `https://softwareequality.com/app-ads.txt` contains `google.com, pub-2980680946304710, DIRECT, f08c47fec0942fa0`.

## 5. Agent installation

- **Linux:** copy `aav-agent-linux-<arch>` to `/opt/aav-agent/aav-agent`, then run `aav-agent enrol --url https://api.softwareequality.com/apps/agentic-antivirus/api --token TOKEN --state /var/lib/aav-agent`. Install `agent/packaging/aav-agent.service` and run `systemctl enable --now aav-agent`.
- **macOS:** copy the binary to `/Library/Application Support/AgenticAntivirus/`, enrol, then load `com.equalitysoftware.aav-agent.plist` with `launchctl bootstrap system`.
- **Windows:** as Administrator, run `aav-agent-windows-<arch>.exe --state C:\ProgramData\AgenticAntivirus enrol …`, then `aav-agent-service-windows-<arch>.exe --startup auto install` and `sc start AgenticAntivirus`.

## Co-hosted deployment (shared VM)
For a VM that already runs another product behind Caddy (the OCI "ai4business" VM with Business AI Manager):
1. `git clone https://github.com/aliabdalla-maker/aepx-core /opt/aepx-core` (or `git -C /opt/aepx-core pull`) and check out the verified commit.
2. `sudo -E /opt/aepx-core/products/agentic-antivirus/deploy/cohost-install.sh`. It adds 2 GB swap if none exists, creates `/etc/aav/aav.env` and the Ed25519 signing key (mode 600/400, never in git), starts the stack with `compose.cohost.yml` (about 1.1 GB memory in total), waits for readiness, then adds the `/apps/agentic-antivirus/` route to the existing Caddyfile. The Caddyfile is backed up first, validated, and restored if Caddy rejects it.
3. Console: `https://api.softwareequality.com/apps/agentic-antivirus/`. Health: `.../api/health`.
Images are also published to GitHub Container Registry by CI: `ghcr.io/aliabdalla-maker/agentic-antivirus-control-plane` and `ghcr.io/aliabdalla-maker/agentic-antivirus-web` (tags: commit SHA, `edge` for the feature branch, `latest` for master, version for `aav-v*` tags).

## Email delivery (verification, password reset, invitations)

Every console page needs a confirmed email address. The control plane queues mail in `aav.outbound_mail`
and a worker sends it over SMTP once these are set in `/etc/aav/aav.env` (root-only; never in git):

```
AAV_SMTP_HOST=smtp.email.<region>.oci.oraclecloud.com
AAV_SMTP_PORT=587
AAV_SMTP_USER=<OCI SMTP credential username>
AAV_SMTP_PASSWORD=<OCI SMTP credential password>
AAV_MAIL_FROM=no-reply@softwareequality.com
AAV_MAIL_DAILY_CAP=90
```

**Google Workspace instead (softwareequality.com mail is on Google):** with 2-Step Verification on the sending
account, create an app password at https://myaccount.google.com/apppasswords and set
`AAV_SMTP_HOST=smtp.gmail.com`, `AAV_SMTP_PORT=587`, `AAV_SMTP_USER` and `AAV_MAIL_FROM` to that address, and
`AAV_SMTP_PASSWORD` to the app password. The domain's SPF record already covers Google, so no DNS change is needed.

OCI Email Delivery is free for up to 100 emails a day (3,000 a month); `AAV_MAIL_DAILY_CAP` keeps the
worker under that, so it cannot create a bill. Setup, in the OCI console (needs approval as a change):

1. Email Delivery > Email Domains: add `softwareequality.com`, then publish its DKIM CNAME and the SPF
   TXT record (`include:<region>.rp.oracleemaildelivery.com`) in DNS.
2. Email Delivery > Approved Senders: add the `AAV_MAIL_FROM` address.
3. Identity > your user > SMTP Credentials: generate one; copy the username and password into the env file.
4. Rerun `deploy/cohost-install.sh`. `/api/ready` then reports `"email_delivery": true`, and mail that
   was queued before is sent on the first pass.

Operator commands (server access required; each is audited as `operator:cli`):

```
cd /opt/aepx-core/products/agentic-antivirus/deploy
docker compose -f compose.yml -f compose.cohost.yml exec control-plane python -m app.admin send-mail
docker compose -f compose.yml -f compose.cohost.yml exec control-plane python -m app.admin verify-email you@example.com
```

`verify-email` is for the operator's own first account or for a support case while delivery is down. It
only confirms an existing account; it never creates one.

## Sign in with Google

The console shows "Continue with Google" when the control plane has a Google OAuth client ID. Google confirms the
email address, so these accounts need no verification email; a first sign-in creates the account and organisation.

1. Google Cloud console > APIs & Services > Credentials > Create credentials > OAuth client ID > Web application.
2. Authorised JavaScript origins: `https://api.softwareequality.com`. No redirect URI and no client secret are used:
   the console receives a Google ID token and the control plane checks its signature, audience and issuer.
3. Add to `/etc/aav/aav.env`, then rerun `deploy/cohost-install.sh`:

```
AAV_OIDC_ISSUER=https://accounts.google.com
AAV_OIDC_CLIENT_ID=<client id>.apps.googleusercontent.com
AAV_OIDC_JWKS_URL=https://www.googleapis.com/oauth2/v3/certs
```

The desktop and mobile apps wrap the web console; Google blocks its sign-in inside embedded web views, so in those
apps people use email and password (or sign in once in the browser console).
