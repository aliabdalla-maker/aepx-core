-- Agent identifiers on the wire (RFC-0001 envelope "sender"/"receiver", e.g.
-- "aepx://agent/console" or "aepx://agent/tutor-1") are often human-readable
-- strings, not just Registry-issued UUIDs. trust_scores.entity_id was
-- UUID-typed, which threw on every non-UUID sender and 500'd the Connector
-- Bus's trust check. Widen it to TEXT — the column never needed the UUID
-- constraint since it's just a lookup key, not a foreign key.
ALTER TABLE trust_scores ALTER COLUMN entity_id TYPE TEXT;
