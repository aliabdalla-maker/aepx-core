---
name: aepx-ci-debug
description: Diagnose and fix failing GitHub Actions CI on aepx-core, including Dependabot PRs and matrix cancellations. Use when a CI run, PR check, or Dependabot bump is red.
---

# Debug aepx-core CI

## 1. Find the real failure

```bash
gh run list --repo aliabdalla-maker/aepx-core --limit 10
gh run view <run-id> --repo aliabdalla-maker/aepx-core --log-failed
```

In a matrix, many jobs showing "cancelled" usually means one job failed and fail-fast cancelled the rest. Find the one genuine failure first; check `strategy.fail-fast` in `.github/workflows/ci.yml` if cascades hide the signal.

## 2. Reproduce locally

Use the `aepx-test-component` skill for the failing matrix entry (same Python 3.11, same pins, `python -m pytest` from the component dir).

## 3. Known failure patterns

| Symptom | Likely cause | Fix |
|---|---|---|
| `ImportError` from `starlette.testclient` | `httpx2` missing | CI installs `httpx2`; make sure the service's requirements don't conflict with it |
| cache/discovery tests fail on Redis | `fakeredis` pin incompatible with bumped `redis` | adjust the `fakeredis==` pin in ci.yml and `requirements-dev.txt` together |
| Dependabot PR fails but master is green | PR branch is stale, missing fixes merged since | `@dependabot rebase` on the PR, or merge master into it |
| `ModuleNotFoundError: app` | bare `pytest` instead of `python -m pytest`, or wrong cwd | run from the component dir with `python -m pytest` |
| ruff findings only in CI | local ruff version differs | use `ruff==0.16.0` |
| platform/* can't import `aepx` | SDK not installed | `pip install -e sdk/python` |

## 4. Fix and verify

- Branch off master, keep the fix minimal, and re-run the failing component locally before pushing.
- Ask before pushing, commenting on PRs or triggering `@dependabot` commands.
- After pushing, watch with `gh run watch <run-id>`.

Jenkins is also configured (`Jenkinsfile`, `docker-compose.jenkins.yml`); check it only if the user mentions Jenkins.
