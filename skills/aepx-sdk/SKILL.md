---
name: aepx-sdk
description: The AEP-X Python SDK (sdk/python/aepx) — Agent, AepxClient, envelopes, the plugin architecture (did/connectors/trust/ledger/audit/chain/oracle + aepx.plugins entry points), and the conformance engine. Use when writing SDK code, a plugin, or SDK tests.
---

# AEP-X Python SDK (`sdk/python/aepx`)

Package `aepx` v0.1.0, Python >=3.11, single runtime dependency `httpx==0.27.0` (`sdk/python/pyproject.toml`). Specified by RFC-0007 (plugins + conformance) and RFC-0008 (chain/oracle plugins).

```
sdk/python/aepx/
  __init__.py        exports Agent, AepxClient, AepxPlugin
  agent.py           Agent — the "pip install aepx" developer experience
  client.py          AepxClient — envelopes, send(), use(), entry-point discovery
  plugins/           base.py + did, connectors, trust, ledger, audit, chain, oracle
  conformance/       checks.py (CHECKS), runner.py (run_conformance)
sdk/python/tests/    conftest.py (FakeAPI), test_client.py, test_plugins.py, test_conformance.py
```

## Install and test

```bash
pip install -e sdk/python          # what CI does for sdk/python and platform/*
cd sdk/python && python -m pytest tests -v
ruff check sdk/python              # CI lints with ruff==0.16.0, rules pinned in ruff.toml
```

Tests use no live services: `conftest.py`'s `fake_api` fixture monkeypatches `aepx.client.httpx.request` and routes by `(method, path-prefix)` via `fake_api.on("GET", "/trust/", body={...})`. Unrouted calls raise `httpx.ConnectError`, which is how the "unreachable" paths are tested.

## AepxClient

`AepxClient(gateway_url, identity_url, trust_url, registry_url, governance_url, bus_url, timeout=10.0, discover_plugins=False)`. Defaults (host ports from the compose stack): gateway `:8000`, identity `:8001`, trust `:8002`, registry `:8003`, governance `:8009`, bus `:8020`. Inside the cluster, pass the service-name URLs explicitly (the platform apps do this from env vars).

- `client.envelope(sender, receiver, payload, message_type="request", metadata=None)` builds an RFC-0001 envelope: `version`, `messageId`, `timestamp`, `sender`, `receiver`, `messageType`, `payload`, `metadata`.
- `client.send(envelope)` POSTs it to `{bus_url}/bus/route` and returns the **raw** `httpx.Response`. A 403 is a protocol outcome (trust or policy denial), not an error.
- `client._request(method, url, **kw)` is the single HTTP choke point every plugin uses (it is what tests patch).

## Agent

```python
from aepx import Agent
agent = Agent("tutor")                  # gateway :8000, registry :8003 by default
agent.execute("Explain Newton's Laws")  # auto-registers, then POST gateway /execute; the result carries a "route" decision
agent.client.did.create()               # full protocol surface via agent.client
```

`register()` POSTs `{"name", "did"}` to Registry `/agents`. If `did` is None, Registry mints a did:key and `agent.did` is filled in from the response.

## Built-in plugins

All seven are attached at construction (`plugins/__init__.py` `BUILTIN_PLUGINS`, in this order; `chain` must come after `connectors` because it delegates to it):

| Attr | Methods | Backing endpoint |
|---|---|---|
| `did` | `create()`, `resolve(did)` (raises `ValueError` on 400) | Identity `POST /did`, `GET /did/{did}` |
| `connectors` | `list()`, `invoke(name, payload, sender="aepx://agent/sdk")` | Bus `GET /health`, `POST /bus/route` |
| `trust` | `get(entity_id)`, `adjust(entity_id, component, delta)` | Trust `GET /trust/{id}`, `POST /trust/{id}/adjust` |
| `ledger` | `anchors(limit=50)`, `verify(audit_id)` | Governance `/ledger/anchors`, `/ledger/verify/{id}` |
| `audit` | `tail(limit=50)`, `policy(risk_level)` | Governance `GET /audit`, `POST /policy/evaluate` |
| `chain` | `read(address, abi, function, args)`, `write(...)`, `rpc(method, params)` | via `connectors.invoke("ethereum", ...)` |
| `oracle` | `decide(prompt, request_id=None)`, `poll()`, `history(limit=50)` | oracle-bridge `/oracle/decide`, `/oracle/poll`, `/oracle/history` |

Things to know:
- `connectors.invoke` never raises on denial. It returns `{"status": 200, ...bus body}` on success, otherwise `{"status", "denied": status in (403, 503), "reason"}`.
- `chain.read`/`chain.write` send payload `{"op": "contract_read"|"contract_write", "address", "abi", "function", "args"}`. `chain.rpc` sends `{"method", "params"}`. All three go through the governed bus, so there is no ungoverned signing path. Signing uses `EVM_PRIVATE_KEY` on the connector side.
- `OraclePlugin(oracle_url="http://localhost:8015")` does not read the client's URLs. To point it elsewhere, re-attach it: `client.use(OraclePlugin(oracle_url=...))`. `platform/aepx-console` does exactly this.

## Writing a plugin

Contract (`plugins/base.py`): an object with an identifier-safe `name` and an `attach(client)` method. Subclass `AepxPlugin` to get `self.client`, `self._get(url)` and `self._post(url)`.

```python
from aepx import AepxClient, AepxPlugin

class EchoPlugin(AepxPlugin):
    name = "echo"
    def say(self, msg):
        return msg

client = AepxClient().use(EchoPlugin())   # use() returns the client
client.echo.say("hi")
```

`use()` raises `ValueError` if `name` is missing or not an identifier, or if it collides with an existing `AepxClient` attribute. Re-using a plugin name that is already registered replaces that plugin.

**Registering for discovery.** Publish under the `aepx.plugins` entry-point group in your package's `pyproject.toml`, the same way the SDK publishes its own built-ins:

```toml
[project.entry-points."aepx.plugins"]
echo = "mypkg.echo:EchoPlugin"
```

Only `AepxClient(discover_plugins=True)` loads entry points. Each entry point is loaded and instantiated with no arguments. A plugin that fails to load is dropped silently (`_discover_entry_point_plugins`), so a broken third-party package cannot break client construction. Add tests next to `tests/test_plugins.py` using the `fake_api` fixture.

## Conformance engine (`aepx.conformance`)

```python
from aepx import AepxClient
from aepx.conformance import run_conformance, CHECKS
report = run_conformance(AepxClient(), ids=["did.roundtrip"])   # ids=None runs everything
report.conformant, report.to_dict()
```

Each `ConformanceCheck(id, rfc, title, run)` returns `CheckResult(PASS|FAIL|SKIP, detail)`. The `_skip_on_unreachable` decorator turns any exception into SKIP. `conformant` means `failed == 0 and passed > 0`. The 12 check IDs and how to add one are covered in `aepx-rfcs-conformance`.

## Related skills

- `aepx-cli` — the `aepx` command built on this SDK
- `aepx-rfcs-conformance` — RFC-0007 check catalogue and the conformance platform
- `aepx-blockchain` — what `chain.*` and `oracle.*` do on the other end
- `aepx-consoles` — workbench, conformance and aepx-console, which embed the SDK
- `aepx-connector-bus` — the `/bus/route` gate that `send`/`invoke` go through
- `aepx-test-component` — running `sdk/python` tests the way CI does
