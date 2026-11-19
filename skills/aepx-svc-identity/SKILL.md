---
name: aepx-svc-identity
description: AEP-X Identity service. It issues HS256 bearer tokens and self-certifying did:key DIDs (RFC-0006) and resolves them. Use when working on, debugging, calling or extending the identity service in aepx-core, or anything touching agent DIDs or /token.
---

# Identity service (`services/identity`)

## Role
Identity issues JWT bearer tokens and Ed25519 `did:key` DIDs, and it resolves a `did:key` back into its DID Document. It hardens Law 1, Identity Before Interaction (see the docstring of `app/did.py`, RFC-0006). The service is stateless: a `did:key` encodes its own public key, so resolving one needs no registry, chain or database lookup. The private key is returned once and never persisted.

## Where
- Code: `services/identity/app/main.py` (routes, JWT) and `services/identity/app/did.py` (did:key encode/decode).
- Compose service: `identity`. Host port `8001` maps to container port `8000`.
- `depends_on: [postgres]` in `docker-compose.yml`, although the code never connects to Postgres.
- Image: `python:3.11-slim`, `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## API
| Method | Path | Purpose | Request / response |
|---|---|---|---|
| GET | `/health` | Liveness | `{"status":"ok","service":"identity"}` |
| POST | `/token` | Issue a JWT | Query param `subject` (required). Returns `{access_token, token_type:"bearer"}`. The payload is `{sub, iat, jti}`, signed HS256, with no `exp` claim. |
| POST | `/did` | Mint a new did:key | No body. Returns `{did, did_document, private_key_hex}`. `did` looks like `did:key:z6Mk...`. |
| GET | `/did/{did}` | Resolve a did:key | Returns the DID Document (`@context`, `id`, `verificationMethod[]` of type `Ed25519VerificationKey2020` with `publicKeyMultibase`, `authentication`, `assertionMethod`). Returns **400** (not 500) for a malformed DID or an unsupported method. |

There is no OpenAPI contract for identity under `schemas/openapi/`.

## Configuration
| Name | Default (from code) | Meaning |
|---|---|---|
| `IDENTITY_JWT_SECRET` | `dev-only-change-me` | HS256 signing secret for `/token`. The code comment says to replace it with Vault before any pilot. |

## Data & dependencies
- No storage: nothing is written to Postgres, Redis or memory.
- It calls no other services and uses no Kafka.
- did:key encoding: the Ed25519 raw public key, with multicodec prefix `0xed 0x01`, base58btc multibase (leading `z`). `resolve_did` accepts only `did:key:z...` whose decoded length is 34 bytes and which carries that prefix. Anything else raises `ValueError`, which the route maps to a 400.
- Callers:
  - `services/registry` calls `POST {IDENTITY_URL}/did` to mint a DID for every agent registered without one. That call is fail-open.
  - `sdk/python/aepx/plugins/did.py` wraps `POST /did` and `GET /did/{did}`.
  - `platform/workbench` and `platform/aepx-console` proxy `/api/did` and `/api/did/{did:path}`.

## Run & test
```bash
pip install -r services/identity/requirements.txt pytest httpx2 ruff==0.16.0
ruff check services/identity
cd services/identity && python -m pytest tests -v
```
Tests: `tests/test_health.py` (health, token) and `tests/test_did.py` (shape, round-trip, uniqueness, 400 on a malformed DID or the `did:ethr` method).

Run it alone:
```bash
cd services/identity && uvicorn app.main:app --port 8001
curl -s -X POST "http://localhost:8001/token?subject=tutor-agent"
DID=$(curl -s -X POST http://localhost:8001/did | python -c 'import sys,json;print(json.load(sys.stdin)["did"])')
curl -s "http://localhost:8001/did/$DID"
```

## Changing it
- The response shape of `POST /did` (`did`, `did_document`, `private_key_hex`) is load-bearing:
  - Registry reads `.get("did")`.
  - The SDK DID plugin and both platform consoles pass it through.
  - Check callers with `grep -rn "identity_url\|IDENTITY_URL\|/did" services connector-bus sdk platform console`.
- Keep bad-input errors as 400. `test_resolve_malformed_did_is_400_not_500` guards this.
- Never persist or log `private_key_hex`. The design returns it exactly once.
- If you add another DID method, `resolve_did` currently rejects anything that is not `did:key`. Update the tests and RFC-0006.
- `/token` has no expiry and no verify endpoint. If you add either, the dev default secret still applies unless `IDENTITY_JWT_SECRET` is set.
- The SDK default URL for identity is `http://localhost:8001` (`sdk/python/aepx/client.py`). Keep the compose port stable.

## Related skills
- aepx-svc-registry (the caller that mints a DID per agent)
- aepx-svc-gateway (aggregates `/health`)
- aepx-run-stack, aepx-test-component, aepx-ci-debug
