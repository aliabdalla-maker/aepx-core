# Signed IdP snapshot connector adapter

This draft adapter authenticates complete bounded JSON snapshots with
HMAC-SHA256, compares signatures in constant time, pins tenant and issuer
against trusted caller configuration, and delegates to the existing
monotonic transactional PostgreSQL snapshot publisher. It also validates
a configured HTTPS snapshot URL against an exact host and default port.

**Not a network client or complete IdP integration.** Caller must supply
authenticated TLS transport, bounded streaming download, strict connect
and total deadlines, redirect disabled, DNS-rebinding/SSRF egress controls,
secret rotation, trusted tenant-to-issuer mapping, independent IdP
membership/revocation source and alerting on stale sync. HMAC key must be
stored in a secret manager, not repository code. Do not use the same
secret across tenants. Monotonic revision replay defense depends on
the PostgreSQL publisher.

Offline tests cover valid signatures, tampering, wrong tenant/issuer,
weak secrets, oversized payloads and unsafe origins. No live service
has been contacted; no production migration, merge, deployment or
external effects have been enabled.
