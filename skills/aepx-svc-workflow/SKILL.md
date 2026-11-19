---
name: aepx-svc-workflow
description: AEP-X Workflow Engine. It creates in-memory multi-step workflows, executes them by resolving each step's agent in Registry, and publishes workflow.completed to Kafka. Use when working on, debugging, calling or extending the workflow service or workflow.completed events in aepx-core.
---

# Workflow Engine (`services/workflow`)

## Role
Workflow holds named workflows made of ordered steps (`capability` and `agent_id`) and executes them sequentially. Each step's output is threaded into the next step's input. On completion it publishes a `workflow.completed` event. That event starts the Tier 2 event chain in `docs/Microservices-Architecture-v2.md` §4.2: Safety and Governance consume it, and Governance audits it under Law 8. `docs/SOA-Architecture.md` makes cross-connector orchestration Workflow's job, not the Connector Bus's.

## Where
- Code: `services/workflow/app/main.py`.
- Compose service: `workflow`. Host port `8007` maps to container port `8000`.
- `depends_on: [registry, memory, neo4j, kafka]`. Compose sets no env vars.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{"status":"ok","service":"workflow"}` |
| POST | `/workflows` | Create a workflow | Body `WorkflowIn {name: str, steps: list[dict]}`. Each step is `{"capability": "...", "agent_id": "..."}`. Returns `{id, status:"CREATED", name, steps}`. |
| POST | `/workflows/{wf_id}/execute` | Run it | For each step it calls `GET {REGISTRY_URL}/agents/{agent_id}`. The result per step is `{capability, agent: <registry JSON>, input: <previous result or {}>}`. Returns the workflow with `status:"COMPLETED"` and `results: [...]`. |

There is no GET-workflow endpoint and no OpenAPI contract.

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `REGISTRY_URL` | `http://registry:8000` | Agent lookup per step (5s timeout) |
| `MEMORY_URL` | `http://memory:8000` | Read into a constant but not used by any route |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Kafka bootstrap for the producer |

## Data & dependencies
- Storage is the in-process dict `_WORKFLOWS`. Workflows are lost on restart and are not shared across replicas. Neo4j is in `depends_on` but not used in code.
- It publishes the Kafka topic `workflow.completed` with `{workflow_id, status:"COMPLETED", step_count, ts}` (JSON). It consumes nothing.
- The producer is lazy and retried (`_get_producer()`). If the broker is unavailable, the event is silently skipped and execution still succeeds.
- Consumers of `workflow.completed`:
  - `services/safety` flags `step_count == 0` to `safety.flagged` as `empty_workflow`.
  - `services/governance` audits it; it is in `_CONSUMED_TOPICS`.
  - The verification and ml-integration consumers are placeholders.
- Failure modes:
  - An unknown `wf_id` raises `KeyError`, which becomes a 500 (not a 404).
  - Registry unreachable returns a 500, and the status stays `RUNNING`.
  - A Registry 404 for a step is not checked and is recorded as that step's `agent`.
- Callers: `platform/aepx-console` (`/api/workflow` create and `/api/workflow/{wf_id}/execute`) and `services/gateway` (`/health`).

## Run & test
```bash
pip install -r services/workflow/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/workflow
cd services/workflow && python -m pytest tests -v
```
Tests: health, and create with empty steps returning `CREATED`. Execute is not tested.

Run it alone:
```bash
docker compose up -d registry kafka
cd services/workflow && REGISTRY_URL=http://localhost:8003 KAFKA_BOOTSTRAP=localhost:9092 uvicorn app.main:app --port 8007
WF=$(curl -s -X POST http://localhost:8007/workflows -H 'content-type: application/json' \
  -d '{"name":"lesson-plan","steps":[{"capability":"generate","agent_id":"<agent-id>"}]}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -X POST http://localhost:8007/workflows/$WF/execute
```
Kafka's advertised listener in compose is `kafka:9092`. From the host you may need to run inside the compose network for the producer to connect.

## Changing it
- The `workflow.completed` payload is a cross-service contract:
  - Safety reads `step_count`.
  - Governance audits the whole event.
  - Find users with `grep -rn "workflow.completed" services connector-bus console`.
- Keep the producer lazy and retried. The code explains that one created at import stays `None` forever after losing the compose startup race.
- If you persist workflows, add a new migration in `schemas/sql/`. None exists for workflows today.
- Consider returning a 404 for an unknown `wf_id` and checking the Registry status. Today both surface as 500 or bad data.

## Related skills
- aepx-svc-registry (the per-step agent lookup)
- aepx-svc-safety (consumes `workflow.completed`)
- aepx-svc-memory (configured, unused)
- aepx-svc-gateway
- aepx-svc-governance (audits `workflow.completed`), aepx-svc-verification, aepx-svc-ml-integration (placeholder consumers)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
