# Connector maturity matrix

From `control-plane/app/routers/integrations.py`. New integrations start as `unavailable`. An integration can be set to `test_only` (its data is labelled simulation everywhere); `verified_live` is refused until a provider adapter is registered in `VERIFIED_ADAPTERS` and sandbox-contract, credential and policy evidence is recorded. Registered verified adapters in this release: 0. Actions that need a provider (suspend account, revoke sessions, apply traffic policy, verify backup) return a failed outcome with the reason instead of pretending to succeed.

AEP-X components used: services/governance `/policy/evaluate` (live, exercised by every action test); connector-bus `/bus/route` to `aepx://connector/ml` (Ollama adapter; tested with a recorded transport, not against a running model).

| Signal | Accepted categories | Path | Maturity now | Needed for verified_live |
|---|---|---|---|---|
| api_gateway | app_layer_flood, automated_abuse, broken_access_control, injection, sensitive_endpoint_misuse | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| backup | backup_failed, backup_verified | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| cdn | app_layer_flood, origin_bypass, origin_unhealthy | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| cloud_audit | privilege_escalation, risky_config_change, suspicious_key_use | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| ddos | app_layer_flood, mitigation_ended, mitigation_started, protocol_exhaustion, reflection_amplification, volumetric_flood | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| dlp | unusual_access, unusual_transfer | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| dns | authoritative_unavailable, malicious_domain, suspicious_query | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| email | malicious_url, phishing_report | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| firewall | blocked_connection, lateral_movement, malicious_destination, port_scan | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| identity | privilege_change, repeated_failures, suspicious_session, unusual_sign_in | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| load_balancer | connection_saturation, origin_unhealthy, packet_rate | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| physical | device_theft, premises_alert | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| url_reputation | malicious_url | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| vulnerability | known_exposure | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
| waf | app_layer_flood, automated_abuse, broken_access_control, injection, sensitive_endpoint_misuse | webhook ingest (canonical schema) | test_only at most | named provider + credentials + sandbox contract test |
