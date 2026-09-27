---
name: aepx-svc-ml-integration
description: ML Integration Service for AEP-X. It holds a prediction and recommendation model registry that is meant to close the Law 9 learning loop, and is currently a placeholder scaffold. Use when working on, debugging, calling or extending the ml-integration service in aepx-core, or when the console's predict panel fails.
---

# ML Integration service (`services/ml-integration`)

## Role
This service owns prediction and recommendation models and the state of the learning loop (docs/Microservices-Architecture-v2.md §3). The Book of Laws names it as the service that closes Law 9 (Learning): Experience → Knowledge → Learning → Improvement.

It is a **scaffold** today:
- predictions are fixed placeholders
- recommendations always return `cache`
- the feedback consumer does nothing

## Where
- Code: `services/ml-integration/app/main.py`.
- Compose service `ml-integration`, host port **8013** -> container 8000, `depends_on: [kafka]`.
- There is no environment block in docker-compose.yml.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{status:"ok", service:"ml-integration"}` |
| POST | `/predict` | Prediction | `PredictIn`: `{model: str, features: dict}`. For a known model it returns `{model, prediction: 0.5, confidence: 0.5, model_version}`. For an unknown model it returns **HTTP 200** with `{error: "unknown model <name>"}` |
| POST | `/recommend` | Route recommendation | `RecommendIn`: `{context: dict}`. It always returns `{recommended_route: "cache", reason: "no trained model yet — defaulting to cheapest safe route"}` |
| GET | `/models` | Model registry | A dict of model name → `{version, trained_at, sample_count}` |

Known models, as keys of `_MODELS`: `cost_prediction`, `demand_prediction` and `workflow_recommendation`. Each is at version `0.1.0`, with `trained_at: null` and `sample_count: 0`.

## Configuration
The code reads no environment variables.

## Data & dependencies
- **Storage:** the in-memory `_MODELS` dict. The planned home is `ml.models` in `schemas/sql/002_v2_additions.sql` (`name PK, version, trained_at, sample_count`), which is not used yet. The docs also mention storing model artifacts in object storage (MinIO), which is not implemented.
- **Kafka:** `kafka-python` is in requirements.txt, but nothing uses it.
  - `consume_feedback_events()` is intended to consume `workflow.completed`, `safety.flagged` and `verification.completed`. It is a `while False` no-op. The thread starts and exits immediately.
  - `ml.prediction.made` is documented as a topic this service publishes, but the code does not publish it.
- **Other services:** it calls none.
- **Callers:** `platform/aepx-console` proxies `/api/models` → `GET /models` and `/api/predict` → `POST /predict`. Gateway and Brain poll `/health`.

## Run & test
```bash
pip install -r services/ml-integration/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/ml-integration
cd services/ml-integration && python -m pytest tests -v
```

Run on its own:
```bash
cd services/ml-integration && uvicorn app.main:app --port 8013
curl -s localhost:8013/health
curl -s localhost:8013/models
curl -s -X POST localhost:8013/predict -H 'Content-Type: application/json' \
  -d '{"model":"cost_prediction","features":{}}'
curl -s -X POST localhost:8013/recommend -H 'Content-Type: application/json' -d '{"context":{}}'
```

## Changing it
- **Keep the console in step.** `platform/aepx-console` `/api/predict` sends `{"model", "features"}`. Its `PredictRequest.model_name()` defaults to `cost_prediction` and maps a legacy `kind` (`"cost"`) to `<kind>_prediction`. Its `predKind` select offers exactly the `_MODELS` keys. If you add or rename a model, update that select too; `test_predict_sends_model_field_ml_integration_expects` in the console's tests guards the payload shape.
- An unknown model returns 200 with an `error` key, not a 4xx. `tests/test_health.py::test_predict_unknown_model` asserts that. Update both if you change it.
- When you implement the feedback consumer:
  - Subscribe to the exact topic names above.
  - Follow the reconnect-loop pattern in `services/governance` `consume_all_events()`. A consumer thread that dies silently makes the learning loop stop without any error.
  - Use `KAFKA_BOOTSTRAP` (default `kafka:9092`), as the other services do.
- If you start publishing `ml.prediction.made` and want it audited, add it to Governance's `_CONSUMED_TOPICS`.
- `/models` returns the raw dict, and the console displays it. Keep its shape, or update `platform/aepx-console`.
- There is no OpenAPI contract in `schemas/openapi/`.
- To find callers: `grep -rn "ML_INTEGRATION_URL\|\"/predict\"\|/models" services connector-bus sdk platform console`.

## Related skills
- aepx-run-stack, aepx-test-component, aepx-ci-debug
- aepx-svc-cost-optimiser: the intended consumer of predictions
- aepx-svc-verification: the source of `verification.completed`
- aepx-svc-governance: topic auditing
- aepx-svc-brain: health monitoring
