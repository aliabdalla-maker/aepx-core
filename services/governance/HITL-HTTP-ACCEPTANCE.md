# HITL HTTP boundary acceptance checklist

This draft adds `POST /hitl/consume` to the Governance FastAPI service.

- A valid, signed OIDC bearer token is required; tenant and `hitl:execute` role are derived exclusively from verified claims.
- The endpoint requires `HITL_DATABASE_URL`; it does not use the governance development `DATABASE_URL` or memory fallback.
- Successful consumption atomically updates the approval and queues an outbox event. **No external tool is executed.**
- Invalid approval, expired approval or action fingerprint mismatch returns 409; persistence failure returns a redacted 503.
- Idempotency keys are restricted to 8–200 ASCII characters (letters, digits, dash, underscore and dot).
- An approval can be consumed once. On a retry after a committed consumption, the API returns the original event ID **only** when tenant, idempotency key, approval ID, action fingerprint and actor all match. Otherwise it returns 409. Concurrency and real PostgreSQL RLS acceptance are still required before automatic retries are enabled.

## Required before merging

1. Run offline HTTP tests: `PYTHONPATH=services/governance python -m unittest discover -s tests -p 'test_hitl_http_boundary.py' -v` with governance dependencies installed.
2. Run PostgreSQL integration tests against a disposable instance using a dedicated non-owner, non-BYPASSRLS role with least-privilege grants.
3. Verify migration order and tenant-aware event foreign key, including two-tenant denial and cross-tenant insertion rejection.
4. Exercise concurrent consumption of the same approval and idempotency key; confirm one durable outbox event.
5. Implement request/decision endpoints with requester/approver separation and verified OIDC identities.
6. Implement the idempotent, fenced outbox dispatcher and dead-letter recovery before enabling execution.
7. Confirm all GitHub Actions checks, obtain review, and perform isolated OCI staging acceptance.

No production deployment is authorised by this PR.
