---
name: aepx-new-service
description: Add a new FastAPI microservice to aepx-core consistent with the repo — layout, /health contract, Dockerfile, docker-compose block and port choice, CI matrix, gateway/console/brain wiring, OpenAPI contract, docs. Use when asked to create, scaffold or register a new AEP-X service.
---

# Add a new AEP-X microservice

This skill is modelled on `services/memory` (smallest) and `services/billing` (a degrade-clean service configured by env vars). All 18 services under `services/` share **byte-identical** Dockerfiles and the same layout.

## 1. Layout

```
services/<name>/
  Dockerfile            # copy verbatim from services/billing/Dockerfile
  requirements.txt
  app/main.py           # `app = FastAPI(...)`; no app/__init__.py, no app/__main__.py anywhere in services/
  tests/test_health.py  # no tests/__init__.py either
```

Dockerfile (the same for every service):

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`requirements.txt`: pin exactly as the other services do. Base set: `fastapi==0.111.0`, `uvicorn[standard]==0.30.0`, `pydantic==2.7.1`, `httpx==0.27.0`. Add only what you use, for example `psycopg[binary]==3.2.1` or `kafka-python==2.0.2` (Governance's pins).

## 2. `app/main.py` and the /health contract

```python
import os
from fastapi import FastAPI

app = FastAPI(title="AEP-X <Name>", version="0.1.0")
TRUST_URL = os.getenv("TRUST_URL", "http://trust:8000")   # deps: env var with in-cluster default

@app.get("/health")
def health():
    return {"status": "ok", "service": "<name>"}
```

- `/health` must return `"status": "ok"`. The Gateway aggregate, the Brain monitor, aepx-console's health grid and the `gateway.health` conformance check all key off that field. Extra fields, such as Governance's `persisted` or Billing's `stripe_configured`, are fine. Never put secrets in them.
- Degrade cleanly. A missing dependency or unset secret must give a well-formed response, never a 5xx. Examples in the repo: Billing's `configured: false`, Governance's in-memory fallback, and oracle-bridge's GREY band.
- Read secrets from env at call time and never return them (see `services/billing`).
- Port 8000 inside the container, always.

## 3. Test (`tests/test_health.py`)

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "<name>"}
```

Tests must pass with no other services running. Use `monkeypatch` on env vars and on `httpx` (as Billing's tests do). Run them the way CI does:

```bash
pip install -r services/<name>/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/<name>
cd services/<name> && python -m pytest tests -v
```

## 4. docker-compose.yml block and port

```yaml
  <name>:
    build: ./services/<name>
    restart: unless-stopped
    ports: ["<host-port>:8000"]
    environment:
      - TRUST_URL=http://trust:8000
    depends_on: [trust]
```

Host ports already in use:
- **Core services:** 8000 gateway, 8001 identity, 8002 trust, 8003 registry, 8004 memory, 8005 cache, 8006 discovery, 8007 workflow, 8008 safety, 8009 governance, 8010 knowledge, 8011 verification, 8012 cost-optimiser, 8013 ml-integration, 8014 brain, 8015 oracle-bridge, 8016 marketplace, 8017 billing.
- **Connector layer:** 8020 connector-bus, 8021–8031 connector categories.
- **GUIs:** 8080 console, 8081 workbench, 8082 conformance, 8083 aepx-console.
- **Infrastructure:** 5432 postgres, 6379 redis, 7474/7687 neo4j, 9092 kafka, 11434 ollama.
- **Optional overlays:** 8545 anvil (chain overlay), 8090 and 50000 Jenkins.
- **docker-compose.test.yml:** 5532, 8100–8103, 8109, 8120, 8122, 8180.

The first unused slot in the core range is **8018** (8019 is also free). Confirm with the user before claiming a port. Also add the port to the port tables in `skills/aepx-run-stack/SKILL.md` and Operational Manual §4.2. Those files are outside this skill's scope, so ask before editing them.

## 5. CI

- `.github/workflows/ci.yml`: add `- <name>` to `jobs.test.strategy.matrix.service`. That job installs requirements, runs `ruff check services/<name>`, then `cd services/<name> && python -m pytest tests -v`.
- `Jenkinsfile`: add `'services/<name>'` to the `components` list, which mirrors the CI matrix.

## 6. Wiring into the platform

- **Gateway:** add `"<name>": os.getenv("<NAME>_URL", "http://<name>:8000")` to `SERVICES` in `services/gateway/app/main.py`, and `- <NAME>_URL=http://<name>:8000` to the gateway's compose `environment`. The env var name is the service name upper-cased with `-` → `_`, as with `COST_OPTIMISER_URL`. Once it is in `SERVICES`, a non-`ok` health **fails** the `gateway.health` conformance check. Also add the env var to the gateway-test block in `docker-compose.test.yml`, pointing at a stub target (`http://identity-test:8000`) like the other unused services there.
- **aepx-console:** add it to `SVC` in `platform/aepx-console/app/main.py` and add its env var to that service's compose block (see `aepx-consoles`).
- **Brain:** to have it health-monitored, add it to `MONITORED_SERVICES` in `services/brain/app/main.py`.
- **Kafka events:** a producer uses `KAFKA_BOOTSTRAP` (default `kafka:9092`). Add every new topic to Governance's `_CONSUMED_TOPICS`, or its events never reach the audit trail.
- **Database:** give it its own schema (database-per-service, Law 10) via a new migration. See `aepx-database`.

## 7. Contract and docs

- **OpenAPI:** `schemas/openapi/` currently holds only `registry.yaml`, a minimal `openapi: 3.0.3` file with `info` and `paths`. Add `schemas/openapi/<name>.yaml` in the same style for the new endpoints.
- **README.md:** add the service to the repository-layout tree and the service count.
- **Operational Manual:** update the port map (§4.2). If the service changes the protocol, write an RFC (see `aepx-rfcs-conformance`).
- **Service skill:** create an `aepx-svc-<name>` skill to match the existing per-service skills.

## Related skills

- `aepx-architecture` — where the service fits
- `aepx-database` — adding its schema migration
- `aepx-test-component`, `aepx-ci-debug` — testing and CI
- `aepx-consoles` — surfacing it in aepx-console
- `aepx-run-stack` — bringing it up
- `aepx-docs` — which docs to update
