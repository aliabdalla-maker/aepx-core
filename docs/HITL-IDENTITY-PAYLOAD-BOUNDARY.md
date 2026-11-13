# Bounded trusted IdP snapshot payload

The new `parse_snapshot_payload` accepts **bytes only** and rejects payloads
larger than 4 MiB before decoding. It requires an exact complete-snapshot
schema, refuses duplicate JSON keys, non-finite numbers, non-integer
revisions and missing timezone information. The optional
`publish_bounded_snapshot` adapter passes validated values into the
existing monotonic transactional publisher.

**This is not an IdP connector.** The caller must separately verify
source authentication and integrity (for example mutually authenticated
transport plus pinned trust configuration), enforce a network timeout and
request-body byte limit before buffering, prevent replay and maintain
complete authoritative revocation data. The current parser does not
validate issuer consistency with a trusted per-tenant configuration; the
publisher performs its own metadata validation. Do not expose a public
snapshot upload endpoint.

No merge, deployment, database migration, OCI spend or external execution.
