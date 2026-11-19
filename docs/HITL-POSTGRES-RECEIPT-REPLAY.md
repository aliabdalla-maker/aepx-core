# Durable signed-receipt replay claims

Apply `services/governance/migrations/20261113_hitl_provider_receipt_claims.sql`
with an approved migration role. Provision a dedicated runtime role with
minimum INSERT and receipt_id SELECT permissions on the claims table and
schema USAGE. The table has global uniqueness on (provider, receipt_id);
never purge claim rows without a documented retention and replay threat model.

Provide a restricted psycopg connection factory to
`postgres_receipt_claimer(connection_factory)`. Pass the resulting callback
to `verify_signed_receipt(...,claim_receipt_id=...)`.

A successful signature check consumes the receipt ID before returning
verified evidence. On duplicate, unavailable database, or malformed IDs,
the callback returns False and verification fails closed.

**Not yet production complete:** apply and test the migration on a staging
PostgreSQL database; confirm permissions and concurrency with multiple
workers; implement an authenticated provider reader and durable evidence
store; integrate with remote reconciliation; and run end-to-end acceptance.
No provider calls or external execution are enabled by this change.

## Isolated concurrent PostgreSQL acceptance

The new `hitl-replay-pg-integration.yml` workflow provisions an ephemeral
PostgreSQL 16 service and runs 24 competing claims for the same receipt.
The acceptance criterion is exactly one successful claim, 23 denials, and
exactly one durable database row. It also checks that distinct receipt IDs
can both be claimed. The workflow has not been executed successfully yet.

The integration test requires both `HITL_REPLAY_TEST_DSN` and
`HITL_REPLAY_ALLOW_ISOLATED_TEST=yes`. **Never point it at production:**
the test creates schema/table objects and writes test rows. Verify the
connection string targets an isolated disposable database before running.

## Integrated verification adapter

`verify_receipt_with_postgres` in `hitl_signed_receipt_postgres.py`
now connects signed receipt validation directly to the durable replay claim
callback. Invalid signatures are rejected before database access. Duplicate
claims and database outages fail closed. This adapter has four additional
offline regression cases. It does not provision a production database or
read provider status over the network. Staging migration and end-to-end
concurrency acceptance remain mandatory before enabling any external effect.
