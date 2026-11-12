# Phase 2.11 security acceptance — draft

Status: **HOLD / NOT APPROVED**. This document does not authorize merging, deployment, or live external forwarding.

## Verified evidence
- Dedicated Hybrid IDE CI at commit `b071daeb`: backend and frontend passed (run 43202685102).
- OpenAI and Anthropic SDK offline integration at `3015f48b`: backend and frontend passed (run 43203741693).
- Negative authentication, destination, and TLS trust tests at `bf90cc5a`: backend and frontend passed (run 43204211752).
- Synthetic MCP JSON-RPC `tools/list` and `tools/call` at `da1d988f`: backend and frontend passed (run 43204529841).

## Pending acceptance gates
- [ ] DNS validation tests pass CI after fixing missing worker source mount at `0c8817b2`. Earlier run 43204863801 failed with FileNotFoundError, not a policy assertion.
- [ ] Verify expired upstream TLS rejection through the actual gateway. A local trusted-but-expired handshake regression was added at `8aa7f505`; CI result pending.
- [ ] Verify expired gateway ingress TLS rejection against the actual gateway listener. A local trusted-but-expired handshake regression was added at `8aa7f505`; CI result pending.
- [ ] Exercise DNS rebinding across a running Docker network, not just injected resolver responses.
- [ ] Verify full repository CI completion; full CI runs have been queued.
- [ ] Independent review of the gateway forwarding policy and network isolation.
- [ ] Review and approve draft PR #25.

## Scope and constraints
All positive and negative tests use isolated Docker networks and synthetic mock services. Test-only fixture forwarding must never be copied to a deployed gateway. No real API keys, paid provider calls, or live MCP tool execution. Production gateway forwarding remains disabled by default.

## Release decision
**HOLD** until all gates pass and an authorized reviewer explicitly approves the release.
