---
name: aepx-test-component
description: Run lint and tests for one or more AEP-X components (services, connector-bus, connector categories, SDK, platform apps, console, Solidity contracts) exactly as CI does. Use before committing or when asked to test a service or connector in aepx-core.
---

# Test an AEP-X component the way CI does

CI (`.github/workflows/ci.yml`) has three jobs, all on Python 3.11, each component in isolation:

| Job | Matrix |
|---|---|
| `test` | services: registry, identity, trust, memory, cache, gateway, discovery, workflow, safety, governance, knowledge, verification, cost-optimiser, ml-integration, brain, oracle-bridge, marketplace, billing |
| `test-soa` | connector-bus, connectors/{enterprise, productivity, devtools, aiplatform, data, messaging, industrial, cloud, government, education, blockchain}, sdk/python, platform/{conformance, workbench, aepx-console}, console |
| `contracts` | tests/test_contracts.py (compiles the real Solidity with solc 0.8.24, runs on an in-memory EVM) |

## Core service (`services/<name>`)

```bash
pip install -r services/<name>/requirements.txt pytest httpx2 ruff==0.16.0
# cache and discovery only:
pip install fakeredis==2.37.0
ruff check services/<name>
cd services/<name> && python -m pytest tests -v
```

`services/cache/requirements-dev.txt` pins `fakeredis==2.23.2`, but CI installs `2.37.0`. Use the CI pin to reproduce CI.

## SOA / SDK / platform / console

```bash
pip install -r <path>/requirements.txt pytest httpx2 ruff==0.16.0
# sdk/python and platform/* also need the SDK installed:
pip install -e sdk/python
ruff check <path>
cd <path> && python -m pytest tests -v
```

`<path>` is one of the `test-soa` matrix entries above.

## Solidity contracts (RFC-0006/0008)

```bash
pip install -r tests/requirements.txt       # web3, py-solc-x, eth-tester
python -m pytest tests/test_contracts.py -v
```

The first run downloads solc 0.8.24. If you change a contract, also update the hand-written ABIs in governance and oracle-bridge (see `aepx-blockchain`).

## The whole matrix, locally

Only when asked; it's slow. One venv per component avoids pin conflicts:

```bash
for c in services/* connector-bus connectors/* sdk/python platform/* console; do
  [ -f "$c/requirements.txt" ] || continue
  python -m venv /tmp/venv-$(basename $c) && . /tmp/venv-$(basename $c)/bin/activate
  pip -q install -r $c/requirements.txt pytest httpx2 ruff==0.16.0
  case $c in services/cache|services/discovery) pip -q install fakeredis==2.37.0;; esac
  case $c in sdk/python|platform/*) pip -q install -e sdk/python;; esac
  ruff check $c && (cd $c && python -m pytest tests -q) || echo "FAILED: $c"
  deactivate
done
```

## Rules

- Always use `python -m pytest`, never bare `pytest`. Tests import `app.main` relative to the component dir, and `-m` puts that dir on `sys.path`.
- The pinned ruff version is 0.16.0, and the config is `ruff.toml` at the repo root. A different version can produce different findings than CI.
- Test what the change touched, plus anything importing it. For example, an SDK change means testing sdk/python and platform/*. A service response-shape change means its callers too; each `aepx-svc-<name>` skill lists them.
- Most service tests run without Postgres, Redis or Kafka and exercise the in-memory fallback. Don't add tests that need live infra to the CI suites.
- Jenkins runs a different, older matrix with different pins (see `aepx-jenkins`). Treat GitHub Actions as the source of truth.

## Related skills

- aepx-ci-debug, aepx-jenkins
- aepx-svc-* and aepx-conn-* (component specifics)
- aepx-blockchain, aepx-sdk
