# Security findings and unresolved acceptance gates

- **High / unverified:** Offline DNS pinning and connection admission contracts do not enforce socket-level destination isolation. Keep external MCP forwarding disabled.
- **High / unverified:** Trusted cryptographic OIDC/JWT verification must be verified at the active dispatch trust boundary.
- **High / unverified:** Worker fencing, single-use HITL and duplicate-billing recovery require end-to-end acceptance evidence.
- **Unknown:** Current CI result is queued; obtain final outcome and logs.

These are acceptance gaps, not confirmed exploitable vulnerabilities.
