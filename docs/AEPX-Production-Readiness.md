# AEP-X production readiness and release evidence

## Current status
**NOT APPROVED FOR PRODUCTION.** Existing reference Compose includes development credentials and exposed ports. A green CI run validates scripts and contracts, not OCI runtime, disaster recovery, CrewAI, MCP or RAG.

## Evidence commands
```bash
bash scripts/aepx-release-evidence.sh
python3 scripts/aepx-static-security.py --production-gate
python3 scripts/aepx-compose-exposure.py --enforce
bash scripts/aepx-dev-acceptance.sh --core
bash scripts/aepx-backup-postgres.sh
```
The two production gates are expected to fail until real hardening is complete. Backups are sensitive; use encryption and protected storage, and test restoration in an isolated environment before setting an RPO/RTO.

## Acceptance matrix
| Capability | Evidence required | Current gate |
| --- | --- | --- |
| Core HTTP | Seven OpenAPI probes in private Codespace | Runtime pending |
| CrewAI | Deterministic multi-agent task, retries, errors | Pending |
| MCP | Allow/deny permissions, timeouts, audit | Pending |
| RAG | Ingest, source citations, negative/hallucination test | Pending |
| HITL | Approve/deny, idempotency, irreversible-action block | Pending |
| Security | No public dev ports, managed secrets, TLS, IAM, scan | Blocked |
| Resilience | Encrypted backup, isolated restore, alerts, RPO/RTO | Pending |
| OCI | Quotas, VCN/network, deployment, rollback, load test | Blocked |
| Release | Named owner approval, rollback drill | Pending |

## Rollout constraints
OCI London VCN quota must be resolved or an approved existing VCN reused before deploying. Never assume the private Codespace is production. Never publish development passwords or backup dumps in CI artifacts. Do not turn production gates into warnings.
