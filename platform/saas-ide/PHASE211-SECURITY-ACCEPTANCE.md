# Phase 2.11 security acceptance — NOT APPROVED

## Delivered
- Separate offline mock billing signer process using an Ed25519 private key file; backend verification uses a pinned public key. A tampered receipt or wrong authority key fails. Existing unique provider-reference DB constraint prevents replay across spend reservations.
- Previous Phase 2.9 PostgreSQL leased worker SIGKILL quarantine, tenant alerts, and Phase 2.10 application default-deny checks remain.
- Existing Docker network-none worker blocks direct internet but cannot call a separate gateway; this is NOT an integrated provider SDK/MCP network topology.

## Mandatory unresolved gates
1. **Actual gateway enforcement**: implement a separately controlled HTTPS proxy, firewall network namespaces/egress ACLs for the actual SDK and MCP workers, and tests proving no direct internet/metadata/DNS/redirect bypass. Never mark a boolean attestation as proof of enforcement.
2. **Billing**: run mock signer in an independently provisioned environment with public-key rotation, request-id persistence, and a reconciliation operator. Mock evidence does not prove real provider charges.
3. **Crash boundaries**: run real SIGKILL at after-reserve, before/after provider dispatch, after settlement and before/after persistence, and assert no replay or double charge.
4. **Authorization**: complete adversarial OIDC/RBAC/RLS/MCP/cancellation matrix across all endpoints.
5. **Release**: both CI workflows green for same SHA; staging restore and rollback, security sign-off, SRE on-call owner, secrets revocation and incident runbook.

## Safety
Keep IDE_EXTERNAL_EXECUTION_ENABLED=false and all other external/MCP execution flags disabled. Draft PR #25 only. Do not merge or deploy.

## Offline topology added in this iteration
`security/phase211-isolated-compose.yml` uses a Docker internal network for the worker, while a distinct gateway placeholder has a second network. CI launches the actual worker container and asserts direct public and metadata sockets fail. The gateway **does not forward traffic**; this is deliberately not a functioning HTTPS egress gateway. Production SDK/MCP traffic tests remain blocked until a real, authenticated forwarding gateway is implemented.
