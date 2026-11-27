"""Live provider adapters (B-06; SEC-01, SEC-02, REC-01, VIS-02, DDOS-01, DDOS-03).

Each adapter talks to one provider's documented API. Adapters are listed in REGISTRY, keyed by
(signal_kind, provider). Being listed means the adapter's request/response contract is covered by tests
(tests/test_providers.py); it does NOT make any tenant's integration live. An integration reaches verified_live
only after its own credentials pass a live health check (POST /v1/integrations/{id}/verify-credentials) and the
sandbox-contract and policy-review evidence is recorded (AX-09).

Credentials are never in config: they are stored write-only and encrypted (PUT /v1/integrations/{id}/secret) and
decrypted only for the call. Every outbound host must pass the egress policy (AAV_EGRESS_ALLOWLIST).

| kind | provider | capabilities | credential |
|---|---|---|---|
| identity | google_workspace | suspend_account, revoke_sessions | service-account JSON (domain-wide delegation) |
| identity | entra_id | suspend_account, revoke_sessions | client secret (config: tenant_id, client_id) |
| cdn / waf / ddos | cloudflare | ip_block, geo_block, challenge (+ rollback) | API token (config: zone_id) |
| firewall | opnsense | ip_block (+ rollback) | "key:secret" (endpoint = firewall URL, config: alias) |
| backup | s3 | verify_backup (newest object age) | "ACCESS_KEY:SECRET_KEY" (config: endpoint, region, bucket, prefix) |
| url_reputation | urlhaus | lookup | abuse.ch Auth-Key |
| url_reputation | google_safe_browsing | lookup | API key |
"""
from __future__ import annotations

from app.providers.base import Provider, ProviderError, Unsupported
from app.providers.cloudflare import Cloudflare
from app.providers.identity import EntraId, GoogleWorkspace
from app.providers.network import OPNsense
from app.providers.reputation import GoogleSafeBrowsing, UrlHaus
from app.providers.storage import S3Backup

REGISTRY: dict[tuple[str, str], type[Provider]] = {
    ("identity", "google_workspace"): GoogleWorkspace,
    ("identity", "entra_id"): EntraId,
    ("cdn", "cloudflare"): Cloudflare,
    ("waf", "cloudflare"): Cloudflare,
    ("ddos", "cloudflare"): Cloudflare,
    ("firewall", "opnsense"): OPNsense,
    ("backup", "s3"): S3Backup,
    ("url_reputation", "urlhaus"): UrlHaus,
    ("url_reputation", "google_safe_browsing"): GoogleSafeBrowsing,
}

__all__ = ["REGISTRY", "Provider", "ProviderError", "Unsupported"]
