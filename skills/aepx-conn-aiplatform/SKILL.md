---
name: aepx-conn-aiplatform
description: AI-platform connector service (connectors/aiplatform) with 14 model-provider connectors, with `ml` as the live self-hosted Ollama adapter and OpenAI, Anthropic, Gemini, Bedrock and others as stubs. Use when invoking the ml connector, debugging Ollama fallback, or adding a model provider.
---

# AI platform connectors (`connectors/aiplatform`)

## Role

LLM and model-serving providers. Every connector is AIA-R1 with min trust 40, so all are allowed by the default policy and reachable by a fresh agent. SOA-Architecture.md §5 made the self-hosted open-weights tier (`ml`) the priority. Commercial connectors stay stubs until usage data shows the local tier needs supplementing (adapter docstring, Law 5).

Risk classes in this category: AIA-R1 x14.

## Where

- Code: `connectors/aiplatform/app/main.py` (routes) and `connectors/aiplatform/app/adapters.py` (`StubAdapter`, specialized adapters, `SPECIALIZED` registry). Tests: `connectors/aiplatform/tests/test_health.py`. Deps: `connectors/aiplatform/requirements.txt` (fastapi==0.111.0, uvicorn[standard]==0.30.0, pydantic==2.7.1, httpx==0.27.0).
- Compose service **`connector-aiplatform`**, host port **8022** -> container 8000, catalogue mounted read-only at `/app/catalogue.json`. Compose sets `OLLAMA_URL=http://ollama:11434` and `OLLAMA_MODEL=llama3.2:1b` and adds `depends_on: [ollama]`.
- `CATEGORY` env: not set in compose. The code default `os.getenv("CATEGORY", "aiplatform")` applies. `CATALOGUE_PATH` defaults to `/app/catalogue.json`.
- The bus reaches it at `http://connector-aiplatform:8000`, overridable with `CONNECTOR_URL_AIPLATFORM` on the connector-bus.

## Connectors

14 connectors, generated from `connectors/catalogue.json`:

| Name | Protocols | ai_risk_class | min_trust_score | maturity |
|---|---|---|---|---|
| `ml` | REST | AIA-R1 | 40 | specialized |
| `vllm` | REST | AIA-R1 | 40 | stub |
| `llamacpp` | REST | AIA-R1 | 40 | stub |
| `lmstudio` | REST | AIA-R1 | 40 | stub |
| `openai` | REST | AIA-R1 | 40 | stub |
| `anthropic` | REST | AIA-R1 | 40 | stub |
| `gemini` | REST | AIA-R1 | 40 | stub |
| `mistral` | REST | AIA-R1 | 40 | stub |
| `cohere` | REST | AIA-R1 | 40 | stub |
| `huggingface` | REST | AIA-R1 | 40 | stub |
| `bedrock` | REST | AIA-R1 | 40 | stub |
| `azure-openai` | REST | AIA-R1 | 40 | stub |
| `vertex-ai` | REST | AIA-R1 | 40 | stub |
| `deepseek` | REST | AIA-R1 | 40 | stub |

## Specialized adapters

### `ml`: `SelfHostedMLAdapter` (Ollama reference; the docstring names vLLM as a drop-in alternative)

- Ops: none are dispatched. The adapter ignores `op` and always performs a completion, reporting `op: "completion"`.
- Payload: `prompt` (default `""`).
- Env: `OLLAMA_URL` (default `http://ollama:11434`), `OLLAMA_MODEL` (default `llama3.2:1b`), `OLLAMA_TIMEOUT` (seconds, default `25`). No credentials.
- Calls `POST {OLLAMA_URL}/api/generate` with `{model, prompt, stream: false}` and returns `result` = the Ollama `response`, plus `model`, `confidence: 0.85`, `estimated_cost: 0.0` and `maturity: "specialized"`.
- If Ollama is unreachable or the model isn't pulled yet, it returns `result: "[fallback: self-hosted model '<model>' unreachable (<ExcType>) — stub completion for prompt of length N]"` with `confidence: 0.3` and `maturity: "specialized_degraded"`. It never returns a 5xx.
- The bus forward timeout is 30s, which is above the default 25s `OLLAMA_TIMEOUT`.

The other 13 connectors (`vllm`, `llamacpp`, `lmstudio`, `openai`, `anthropic`, `gemini`, `mistral`, `cohere`, `huggingface`, `bedrock`, `azure-openai`, `vertex-ai`, `deepseek`) use `StubAdapter`.

## API

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | `{status: "ok", service: "connector-aiplatform", adapters: <catalogue names ∪ SPECIALIZED>, specialized: <SPECIALIZED names>}` |
| POST | `/connector/execute` | Body: RFC-0001 envelope (`sender`, `receiver`, `payload` required). Name = last segment of `receiver`. Dispatch order: `SPECIALIZED[name]`, then `StubAdapter` if the name is catalogued under `aiplatform`, otherwise 404 `connector '<name>' is not registered in category 'aiplatform'`. Only `payload` is passed to the adapter. |

If the catalogue isn't mounted, `MY_CONNECTORS` is empty: specialized adapters still work, but stub dispatch returns 404. Call this service through the bus. Direct calls skip trust, policy and audit.

## Run & test

CI-matching (`.github/workflows/ci.yml`, job `test-soa`, Python 3.11):

```bash
pip install -r connectors/aiplatform/requirements.txt pytest httpx2 ruff==0.16.0
ruff check connectors/aiplatform
cd connectors/aiplatform && python -m pytest tests -v
```

Tests: health, 14 catalogue entries, stub dispatch (`deepseek`), unknown 404, `ml` degraded without Ollama, and `ml` live with mocked `httpx.post`. The tests point `CATALOGUE_PATH` at the repo's `connectors/catalogue.json`.

Invoke via the bus (stack up, bus on :8020):

```bash
curl -s localhost:8022/health
curl -s -X POST localhost:8020/bus/route -H 'Content-Type: application/json' \
  -d '{"sender":"aepx://agent/cli","receiver":"aepx://connector/ml","payload":{"prompt":"Explain Newtons second law"}}'
```

If Ollama is still pulling the model, `response.maturity` is `specialized_degraded`.

## Adding a real adapter here

- For another self-hosted server (`vllm`, `llamacpp`, `lmstudio`), mirror `SelfHostedMLAdapter`: take the URL, model and timeout from env with in-code defaults, and fall back to `specialized_degraded` on any exception.
- A commercial provider needs an API-key env var added to `.env.example` and to `connector-aiplatform`'s `environment:`. With no key, degrade rather than raise. Keep the forward under the bus's 30s timeout.
- SOA-Architecture.md §3.2 says the Universal Cost Optimiser should be consulted before metered calls. That is not wired in this service's code today.
- Then: set `maturity: "specialized"` in `catalogue.json`, add tests for each op plus the unsupported-op and no-credentials paths, and regenerate docs/Connector-Catalogue.md. Full procedure: the `aepx-connector-adapter` skill.

## Related skills

- `aepx-connector-bus`: trust/policy/circuit gate and routing in front of this service.
- `aepx-connector-adapter`: full add/upgrade-connector procedure.
- `aepx-test-component`: CI-matching test runs.
- `aepx-governance-policy`: the `max_risk_level` policy that decides which risk classes pass.
