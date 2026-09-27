---
name: aepx-jenkins
description: The opt-in Jenkins CI for aepx-core — Jenkinsfile stages, jenkins/Dockerfile, plugins.txt, docker-compose.jenkins.yml, running Jenkins locally, and how it differs from GitHub Actions CI. Use when running, editing or debugging the Jenkins pipeline.
---

# Jenkins CI (opt-in)

GitHub Actions (`.github/workflows/ci.yml`) is the main CI. Jenkins is a second, local pipeline, kept out of `docker-compose.yml` and **not started by default**. The reason, per the compose file header: the host has measured as low as ~600MB free RAM with the full stack running, and Jenkins wants 512MB–1GB+ of heap.

## Files

- **`docker-compose.jenkins.yml`**: a single `jenkins` service built from `./jenkins`.
  - Ports `8090:8080` (web UI) and `50000:50000` (inbound agents).
  - `JAVA_OPTS=-Xmx768m -Xms256m`.
  - Volumes: `jenkins-home:/var/jenkins_home` and **`/var/run/docker.sock:/var/run/docker.sock`**.
- **`jenkins/Dockerfile`**: `FROM jenkins/jenkins:lts-jdk17`. As root it installs `python3`, `python3-pip`, `python3-venv`, `docker-ce-cli` and `docker-compose-plugin` (the CLI only, no nested dockerd), then preinstalls plugins with `jenkins-plugin-cli --plugin-file`, and finally switches back to `USER jenkins`.
- **`jenkins/plugins.txt`**: `workflow-aggregator`, `git`, `github`, `github-branch-source`, `docker-workflow`, `pipeline-stage-view`, `credentials-binding`, each pinned to `:latest`.
- **`Jenkinsfile`**: a declarative pipeline, `agent any`, with options `timestamps()` and `disableConcurrentBuilds()`, and env `COMPOSE_PROJECT_NAME=aepx-ci`.

## Pipeline stages

1. **Lint + Unit Tests**: a `parallel` branch per component. Each branch:
   - creates its own venv at `$WORKSPACE/.venv-<dir>`;
   - runs `pip install -r <dir>/requirements.txt pytest==8.2.0 ruff`;
   - installs `fakeredis==2.23.2` for cache and discovery, and `pip install -e sdk/python` for `sdk/python` and `platform/*`;
   - runs `ruff check <dir>`, then `(cd <dir> && pytest tests -v)`, then deletes the venv.
2. **Build Images**: `docker compose build`. This is build-only: the build context is streamed to the host daemon, so it is safe over the mounted socket.
3. **v1 Integration Smoke Test**: `bash tests/v1/run_smoke_test.sh`. The script brings up `docker-compose.test.yml` as project `aepx-test` on ports 8100–8180, exercises identity → trust → registry → gateway → governance → bus → aiplatform → console against the **main stack's Ollama** via `host.docker.internal:11434`, and tears itself down unless you pass `--keep`.

`post.always` runs `docker compose -p ${COMPOSE_PROJECT_NAME} -f docker-compose.test.yml down -v --remove-orphans || true`. That uses project `aepx-ci`, while the smoke script uses `aepx-test`. The script's own EXIT trap does the real teardown.

**Docker-outside-of-Docker constraint** (Jenkinsfile header): lint and tests run natively in the Jenkins image, because a nested `docker run -v` or `compose up` with relative bind mounts would resolve against the host filesystem, not the workspace. Keep new stages build-only, or drive containers over HTTP.

## Running Jenkins locally

```bash
# free RAM first if the main stack is up, e.g. stop some connector categories
docker compose -f docker-compose.jenkins.yml up -d --build
# UI: http://localhost:8090 — complete the setup wizard and set a real admin password
```

Then create a **Pipeline script from SCM** (or Multibranch Pipeline) job pointing at the repo's GitHub remote. The Jenkinsfile says the one-time setup steps are in `docs/Operational-Manual.html`, but that document contains no Jenkins section, so ask the user for any job, credential or webhook details. The smoke stage needs the main stack's Ollama running and warm on host port 11434.

**Security:** the socket mount gives Jenkins root-equivalent control of the host. Set an admin password and never expose port 8090 outside a trusted network.

## Jenkins vs GitHub Actions

| | GitHub Actions `ci.yml` | Jenkinsfile |
|---|---|---|
| Trigger | every push and pull_request | whatever the Jenkins job is configured with |
| Components | `test`: 18 services; `test-soa`: bus, 11 connector categories, `sdk/python`, 3 platform apps, `console` | 15 services, bus, 11 categories, console, `sdk/python`, `platform/conformance`, `platform/workbench` |
| Missing from Jenkins | — | `oracle-bridge`, `marketplace`, `billing`, `platform/aepx-console`, and the `contracts` job (`tests/test_contracts.py`) |
| Tool pins | `ruff==0.16.0`, `pytest` unpinned, `httpx2`, `fakeredis==2.37.0` | `ruff` unpinned, `pytest==8.2.0`, no `httpx2`, `fakeredis==2.23.2` |
| Test command | `python -m pytest tests -v` (puts the component dir on sys.path) | venv `pytest tests -v` |
| Extra stages | — | image build and the v1 integration smoke test |

When you add a component to `ci.yml`, also add it to the Jenkinsfile's `components` list. The existing gaps above are drift, not intentional exclusions. No reason for them is documented, so ask the user before closing them. Because `ruff` is unpinned here, Jenkins may run a different ruff version than CI. `ruff.toml` pins the rule selection (E4, E7, E9, F), which limits but does not remove that drift.

## Related skills

- `aepx-ci-debug` — GitHub Actions failures
- `aepx-test-component` — running one component's lint and tests the CI way
- `aepx-run-stack` — the main stack whose Ollama the smoke test reuses
- `aepx-new-service` — where to register a new component in both pipelines
