# Trusted tenant authorization context: offline contract only

`scripts/aepx_trusted_tenant_context.py` implements a **pure** HMAC-SHA256 authorization context with canonical tenant UUID, principal, fixed audience, allowlisted action, issue/expiry (maximum five minutes), nonce and constant-time signature comparison. Its verifier denies missing/unknown fields, tampering, scope mismatch, weak keys, invalid times and expiry.

This is **not a production authentication solution**. A caller can sign arbitrary claims if it possesses the key. The key must exist only in an independently authenticated trusted controller. The service must derive tenant/principal from verified OIDC identity and trusted tenant membership, not request body, HTTP headers, or `SET app.tenant_id`. The controller must bind a single-use nonce to a transactional PostgreSQL record and enforce role grants, authenticated reviewer authorization, immutable artifact verification, live fence and atomic approval consumption/completion.

**No database function currently consumes this contract.** No trusted completion is enabled; the existing spoofable tenant GUC remains unsafe. This change includes offline tests only, not a PostgreSQL integration or a claim that 10,000 engineering iterations have run.
