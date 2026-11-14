# Offline reviewed evidence attestation

The offline verifier `scripts/aepx_reviewed_evidence_attestation.py` first checks the five stage artifact bytes against the reviewed local ledger, then verifies an HMAC-SHA256 signature over a canonical envelope containing tenant UUID, iteration number, current lease fence, worker ID, reviewer ID, expiry and all five SHA-256 stage digests.

The trusted signing service must authenticate the reviewer and verify the current PostgreSQL lease before issuing a signature. The HMAC key must remain inside a trusted service, never in an untrusted agent or worker. This verifier does not issue approvals, prove human review, verify test success, revoke signatures, prevent replay, lock immutable evidence or perform any database transition. The current lease fence is supplied by the caller and must be checked independently against trusted database state. **PostgreSQL completion remains fail-closed.**

Next: bind an immutable evidence snapshot and attestation to a trusted PostgreSQL transaction; authenticate tenant/reviewer identity; implement single-use approval consumption and revocation; test replay, key rotation and concurrent claims in disposable PostgreSQL. Do not use this prototype as production authorization.
