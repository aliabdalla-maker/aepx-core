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
