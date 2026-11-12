# AEP-X Phase 2.21 controlled release checklist

Release status: HOLD. No cloud resources provisioned, no public website changes, no app-store uploads.

## OCI UK London
- [ ] Verify tenancy, compartment, Object Storage namespace, limits and budget
- [ ] Validate Terraform without credentials
- [ ] Review plan and resource costs
- [ ] Obtain explicit approval before apply
- [ ] Provision separate staging only; private networking, no public API or gateway forwarding
- [ ] Configure secret manager, DNS, TLS, OIDC, database, backups and monitoring

## Desktop and website
- [ ] Execute manual build matrix on Windows/macOS/Linux
- [ ] Sign Windows binaries, notarize macOS, sign Linux packages as appropriate
- [ ] Produce SHA-256 manifest and verify every binary
- [ ] Test installation, upgrade, uninstall, accessibility and authentication
- [ ] Upload verified artifacts to approved download hosting
- [ ] Deploy website downloads page only after links are verified

## Android
- [ ] Build PNG icons and verified production web manifest
- [ ] Create Android TWA project and compile signed AAB
- [ ] Confirm package ID and Google Play App Signing SHA-256
- [ ] Deploy assetlinks.json with actual fingerprint
- [ ] Complete Data safety, privacy policy, store listing and internal testing
- [ ] Review Play Console before any production release

## Marketplaces
- [ ] VS Code: register publisher, test extension, package and submit for review
- [ ] JetBrains: implement Kotlin plugin, test compatibility, sign and submit
- [ ] ChatGPT Apps: validate current platform SDK and OAuth account linking; do not assume OpenAPI alone constitutes a valid app
- [ ] Review security scopes, support and privacy terms for each marketplace

## Final gates
- [ ] Full CI green on final commit
- [ ] Independent penetration/security review
- [ ] Provider signed receipts and idempotency verified end-to-end
- [ ] Release approval documented
