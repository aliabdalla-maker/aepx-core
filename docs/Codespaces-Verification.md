# Codespaces runtime verification and security

The repository CI builds the existing console and verifies its OpenAPI endpoint. It does **not** run the complete backend. A private Codespace is required for backend integration testing.

```bash
git switch master
git pull --ff-only origin master
bash scripts/codespaces.sh start
bash scripts/codespaces-smoke.sh
bash scripts/codespaces-security-check.sh
# Only after reviewing published ports and development credentials:
bash scripts/codespaces.sh core
bash scripts/codespaces-smoke.sh --core
```

The core smoke test checks that expected containers are running and that selected Python/FastAPI services respond locally. It does not validate agent workflows, MCP calls, payments, or production readiness. For failed checks use `bash scripts/codespaces.sh diagnose` and `bash scripts/codespaces.sh core-logs`.

Never publish the existing core stack externally: its Compose definition contains development credentials and published service ports. Keep Codespaces ports private. For production, create separate infrastructure and a hardened Compose/Kubernetes configuration with secret management, HTTPS, RBAC, monitoring, backups and integration tests.
