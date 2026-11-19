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

## Experimental CONNECT gateway (added)
`security/egress_gateway.py` implements an authenticated HTTP CONNECT tunnel restricted to explicit hostname allowlists and TCP 443, resolves a single globally routable IP and pins that socket destination, and rejects other methods. It does not terminate TLS: SDK/MCP clients must verify TLS hostname certificates themselves. The gateway has an independent bearer credential and a separate forwarding switch. Compose mounts it with forwarding **disabled**, no allowlist, and no credential; it cannot send traffic by default. Unit tests cover private/metadata DNS, mixed DNS, malformed hosts and arbitrary ports.

**Still not a verified end-to-end production gateway:** actual SDKs are not wired to this proxy, the MCP adapter expects an HTTPS proxy whereas this gateway accepts plaintext HTTP CONNECT over the private Docker network, and the existing Compose test only proves worker direct-socket denial. An authenticated TLS-wrapped proxy and actual SDK/MCP transport tests are required before enabling. Redirect handling must be enforced at clients and separately tested. Do not set forwarding or external execution flags.

## Transport integration increment
`backend/app/transport211.py` now supplies explicit httpx HTTP CONNECT clients using the dedicated `http://gateway:8080` internal-network endpoint, a separate gateway bearer credential, no ambient proxy variables, and no redirects. OpenAI and Anthropic SDK clients use this transport; MCP's HTTP transport uses its asynchronous counterpart. Gemini and OCI fail closed until their SDK transports can be audited and routed through the same gateway. External execution and forwarding remain disabled in Compose.

**Unverified:** the gateway is not yet an HTTPS-encrypted worker-to-gateway proxy, there is no end-to-end real SDK/MCP Docker transport test, and the gateway is not yet hardened against every HTTP CONNECT parsing/tunnelling bypass. Treat this as an experimental integration, not release acceptance.
