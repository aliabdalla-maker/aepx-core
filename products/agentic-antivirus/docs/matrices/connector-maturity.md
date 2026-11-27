# Connector maturity matrix

From `control-plane/app/routers/integrations.py`. New integrations start as `unavailable`. An integration can be set to `test_only` (its data is labelled simulation everywhere); `verified_live` is refused until a provider adapter exists (`app/providers`, contract-tested in `tests/test_providers.py`), the integration's own encrypted credential passed a live `verify-credentials` check in the last 24 h, and sandbox-contract and policy evidence is recorded. Provider adapters in this release: 9 (kind/provider pairs). Actions that need a provider (suspend account, revoke sessions, apply traffic policy, verify backup) return a failed outcome with the reason instead of pretending to succeed.

AEP-X components used: services/governance `/policy/evaluate` (live, exercised by every action test); connector-bus `/bus/route` to `aepx://connector/ml` (Ollama adapter; tested with a recorded transport, not against a running model).

| Signal | Accepted categories | Path | Provider adapters | Path to verified_live |
|---|---|---|---|---|
| api_gateway | app_layer_flood, automated_abuse, broken_access_control, injection, sensitive_endpoint_misuse | webhook ingest (canonical schema) | none yet | test_only at most |
| backup | backup_failed, backup_verified | webhook ingest (canonical schema) | s3 | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
| cdn | app_layer_flood, origin_bypass, origin_unhealthy | webhook ingest (canonical schema) | cloudflare | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
| cloud_audit | privilege_escalation, risky_config_change, suspicious_key_use | webhook ingest (canonical schema) | none yet | test_only at most |
| ddos | app_layer_flood, mitigation_ended, mitigation_started, protocol_exhaustion, reflection_amplification, volumetric_flood | webhook ingest (canonical schema) | cloudflare | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
| dlp | unusual_access, unusual_transfer | webhook ingest (canonical schema) | none yet | test_only at most |
| dns | authoritative_unavailable, malicious_domain, suspicious_query | webhook ingest (canonical schema) | none yet | test_only at most |
| email | malicious_url, phishing_report | webhook ingest (canonical schema) | none yet | test_only at most |
| firewall | blocked_connection, lateral_movement, malicious_destination, port_scan | webhook ingest (canonical schema) | opnsense | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
| identity | privilege_change, repeated_failures, suspicious_session, unusual_sign_in | webhook ingest (canonical schema) | entra_id, google_workspace | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
| load_balancer | connection_saturation, origin_unhealthy, packet_rate | webhook ingest (canonical schema) | none yet | test_only at most |
| physical | device_theft, premises_alert | webhook ingest (canonical schema) | none yet | test_only at most |
| url_reputation | malicious_url | webhook ingest (canonical schema) | google_safe_browsing, urlhaus | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
| vulnerability | known_exposure | webhook ingest (canonical schema) | none yet | test_only at most |
| waf | app_layer_flood, automated_abuse, broken_access_control, injection, sensitive_endpoint_misuse | webhook ingest (canonical schema) | cloudflare | per integration: stored credential + live verify-credentials + sandbox/policy evidence |
