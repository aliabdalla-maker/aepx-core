# Offline signed authorization replay ledger

`scripts/aepx_authz_nonce_ledger.py` combines the existing signed tenant context verifier with a local SQLite consumed-context ledger. It uses `BEGIN IMMEDIATE`, a unique SHA256 fingerprint of canonical claims plus signature, and an atomic INSERT to deny repeated consumption across connections. Tests cover duplicate use, concurrent attempts, tampering, expiry and invalid database paths.

**Strict scope:** local single-host development tests only. This component does not authenticate an OIDC principal, establish tenant membership, make `app.tenant_id` trustworthy, verify reviewer approval, or protect an external action atomically. In particular, a process crash after consumption but before a separate business action can strand authorization; a process that copies or replaces the SQLite file can bypass the local ledger. Use a trusted database transaction with single-use nonce consumption and the protected state transition for production. Do not use this module to authorize provider dispatch, financial charges or iteration completion.

The repository workflow runs offline tests. No PostgreSQL runtime or production deployment has been performed.

## Connection lifecycle hardening

The SQLite connection is now explicitly closed on successful consumption and on rejected replay. Failed transactions explicitly roll back, and Boolean or noninteger injected clocks are denied. The offline regression tests cover connection cleanup on both success and replay. This does not address database-file substitution, distributed replay, or the lack of atomicity with a protected PostgreSQL operation. No runtime CI results have been verified.
