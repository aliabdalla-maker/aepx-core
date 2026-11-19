# Signed provider receipts — integration contract

`verify_signed_receipt` validates HMAC-SHA256 over the **original raw bytes**,
strict receipt schema, provider identity, timestamp freshness and a durable
single-use receipt ID. It does not contact providers or execute actions.

Provision a unique >=32-byte secret per provider from a secrets manager.
Authenticate provider transport and isolate egress. Rotate keys with an
explicit versioned transition policy; never accept arbitrary client keys.

The `claim_receipt_id` callback MUST perform an atomic, durable uniqueness
claim in a tenant-aware database. Do not use an in-memory set. An invalid,
unavailable or duplicate claim fails closed. Claims are consumed before the
verified receipt is returned; design retries to handle an already-claimed
receipt via an independently audited stored status, never by blindly
accepting the same signed payload twice.

The caller must persist and independently read the verified status from a
trusted receipt store. Pass that store reader to `provider_evidence_verifier`.
Do not construct evidence from the reconciliation HTTP request.

This implementation is a protocol-specific reference verifier. Real MCP
providers may not support HMAC receipts: their authenticated status API or
asymmetric signed evidence must be validated with a provider-specific
adapter. No production connector, replay database migration, or network
credentials are included. External execution remains disabled.
