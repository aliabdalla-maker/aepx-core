# Bounded authoritative identity snapshot ingestion

The snapshot publisher now uses `itertools.islice` to bound iterable
materialisation at 100,001 memberships and 1,000,001 revocations,
then rejects over-limit snapshots before issuing SQL. Infinite
generators therefore cannot exhaust memory indefinitely.

Issuer metadata must use HTTPS with a host, no userinfo, query, fragment,
whitespace or non-root path. The trusted synchronizer must canonicalise
issuer identifiers consistently with OIDC configuration.

This mitigates unbounded iterator memory exhaustion; it does not
guarantee bounded execution time if an iterator blocks forever, nor
prevent large but in-limit payloads. Next: enforce upstream byte/time
limits and streaming batch ingestion under one transaction.

The changes are isolated in a draft PR. No production migration,
merge, deployment or external execution is enabled.
