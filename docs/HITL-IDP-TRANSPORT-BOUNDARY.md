# Trusted IdP transport boundary

This change introduces an **injectable** fail-closed transport boundary.
It validates an HTTPS URL against an exact configured hostname, requests
a maximum 4 MiB body, requires a maximum three-second connection deadline
and ten-second total deadline, explicitly disallows redirects, rejects
non-200 responses and any changed final URL, and forwards successful
responses to the HMAC-authenticated snapshot publisher.

**Security limit:** These are interface requirements and post-fetch checks.
The supplied `fetch` implementation must independently enforce byte
limits during streaming, TLS certificate validation, no redirects, DNS
rebinding/SSRF controls, allowlisted egress and real connect/total timeouts.
The module deliberately does not supply a default network client.
A malicious or broken fetcher can violate these requirements; therefore
do not enable live IdP synchronization until a reviewed network adapter
and integration tests are available.

No live requests, OCI resources, merge, deployment or production DB
changes were performed.
