---
name: aepx-test-component
description: Run lint and tests for one or more AEP-X components (services, connector-bus, connector categories, SDK, platform apps, contracts) exactly as CI does. Use before committing or when asked to test a service or connector in aepx-core.
---

# Test an AEP-X component the way CI does

CI (`.github/workflows/ci.yml`) runs every component in isolation on Python 3.11. Reproduce that locally so results match.

## Core service (`services/<name>`)

```bash
pip install -r services/<name>/requirements.txt pytest httpx2 ruff==0.16.0
# cache and discovery only:
pip install fakeredis==2.37.0
ruff check services/<name>
cd services/<name> && python -m pytest tests -v
```

## SOA / SDK / platform (`connector-bus`, `connectors/<category>`, `sdk/python`, `platform/<app>`, `console`)

```bash
pip install -r <path>/requirements.txt pytest httpx2 ruff==0.16.0
# sdk/python and platform/* also need the SDK installed:
pip install -e sdk/python
ruff check <path>
cd <path> && python -m pytest tests -v
```

## Solidity contracts (RFC-0006/0008)

```bash
pip install -r tests/requirements.txt
python -m pytest tests/test_contracts.py -v
```

## Rules

- Always `python -m pytest`, never bare `pytest`: tests import `app.main` relative to the component dir, and `-m` puts that dir on `sys.path`.
- Use a fresh venv per component when pins conflict; components pin independently.
- The pinned ruff version is 0.16.0 — a different version can produce different findings than CI.
- Run the whole matrix only when asked; otherwise test what the change touched plus anything importing it (e.g. an SDK change → sdk/python and platform/*).
