---
name: aepx-ci-debug
description: Diagnose and fix failing GitHub Actions CI on aepx-core, including Dependabot PRs, matrix cancellations, lint failures and the Solidity contracts job. Use when a CI run, PR check, or Dependabot bump is red.
---

# Debug aepx-core CI

The workflow is `.github/workflows/ci.yml` and runs on every push and pull request. It has three jobs: `test` (18 services), `test-soa` (bus, 11 connector categories, SDK, 3 platform apps, console) and `contracts`. Matrix contents: `aepx-test-component`.

## 1. Find the real failure

```bash
gh run list --repo aliabdalla-maker/aepx-core --limit 10
gh run view <run-id> --repo aliabdalla-maker/aepx-core --log-failed
```

The matrices don't set `fail-fast`, so GitHub's default (`true`) applies. One failing entry cancels the rest of its job, so many "cancelled" jobs usually hide a single real failure. Find that one first. To see every failure in one run, set `strategy.fail-fast: false` on a branch, and ask before changing it on master.

## 2. Reproduce locally

Use `aepx-test-component` for the failing matrix entry: Python 3.11, the same pins, and `python -m pytest` from the component dir.

## 3. Known failure patterns

| Symptom | Likely cause | Fix |
|---|---|---|
| `ImportError` from `starlette.testclient` | `httpx2` missing | CI installs `httpx2`. Make sure the service's requirements don't conflict with it. |
| cache/discovery tests fail on Redis | `fakeredis` pin incompatible with bumped `redis` | Adjust the `fakeredis==` pin in ci.yml, and align `services/cache/requirements-dev.txt` (currently 2.23.2 vs CI's 2.37.0). |
| Dependabot PR fails but master is green | PR branch is stale and missing fixes merged since | Comment `@dependabot rebase` on the PR, or merge master into it. |
| `ModuleNotFoundError: app` | bare `pytest` instead of `python -m pytest`, or wrong cwd | Run from the component dir with `python -m pytest`. |
| ruff findings only in CI | local ruff version differs | Use `ruff==0.16.0` with the repo's `ruff.toml`. |
| platform/* or sdk tests can't import `aepx` | SDK not installed | `pip install -e sdk/python` |
| `contracts` job: solc download or compile error | solc 0.8.24 fetch failed, or a contract change broke compilation | Re-run once for network flakes. Otherwise reproduce with `python -m pytest tests/test_contracts.py -v` (see `aepx-blockchain`). |
| A Dependabot bump breaks many services at once | a shared pin (fastapi, starlette, pydantic, httpx) moved | Fix one service, then apply the same pin change across all `requirements.txt` in a single PR. |

## 4. Fix and verify

- Branch off master, keep the fix minimal, and re-run the failing component locally before pushing.
- Ask before pushing, commenting on PRs or triggering `@dependabot` commands.
- After pushing, watch with `gh run watch <run-id> --repo aliabdalla-maker/aepx-core`.
- If the fix touches plugin skills, cut a plugin release too (see `scripts/release_plugin.py`).

Jenkins (`Jenkinsfile`) runs a separate, older matrix with different pins, so a Jenkins result can differ from Actions. Check it only if the user mentions Jenkins (`aepx-jenkins`).

## Related skills

- aepx-test-component, aepx-jenkins
- aepx-blockchain, aepx-svc-*
