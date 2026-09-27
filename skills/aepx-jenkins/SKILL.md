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
  - Volumes: `${JENKINS_HOME_MOUNT:-jenkins-home}:/var/jenkins_home` and **`/var/run/docker.sock:/var/run/docker.sock`**.
  - `group_add: ["${DOCKER_GID:-999}"]`, so the jenkins user can use the socket, and `extra_hosts: host.docker.internal:host-gateway`, so the smoke stage can reach the host's published ports.
- **`jenkins/Dockerfile`**: `FROM jenkins/jenkins:lts-jdk17`. As root it installs `python3`, `python3-pip`, `python3-venv`, `docker-ce-cli` and `docker-compose-plugin` (the CLI only, no nested dockerd), then preinstalls plugins with `jenkins-plugin-cli --plugin-file`, and finally switches back to `USER jenkins`.
- **`jenkins/plugins.txt`**: `workflow-aggregator`, `git`, `github`, `github-branch-source`, `docker-workflow`, `pipeline-stage-view`, `credentials-binding`, each pinned to `:latest`.
- **`Jenkinsfile`**: a declarative pipeline, `agent any`, with options `timestamps()` and `disableConcurrentBuilds()`, and env `COMPOSE_PROJECT_NAME=aepx-ci`.

## Pipeline stages

1. **Lint + Unit Tests**: a `parallel` branch per component. Each branch:
   - creates its own venv at `$WORKSPACE/.venv-<dir>`;
   - runs `pip install -r <dir>/requirements.txt pytest httpx2 ruff==0.16.0`;
   - installs `fakeredis==2.37.0` for cache and discovery, and `pip install -e sdk/python` for `sdk/python` and `platform/*`;
   - runs `ruff check <dir>`, then `(cd <dir> && python -m pytest tests -v)`, then deletes the venv.
2. **Contracts**: `pip install -r tests/requirements.txt` in its own venv, then `python -m pytest tests/test_contracts.py -v` (same as the Actions `contracts` job).
3. **Build Images**: `docker compose build`. This is build-only: the build context is streamed to the host daemon, so it is safe over the mounted socket.
4. **v1 Integration Smoke Test**: `bash tests/v1/run_smoke_test.sh` inside `withEnv(['AEPX_TEST_HOST=host.docker.internal'])`. The script reads `AEPX_TEST_HOST` (default `localhost`) for every test-port and Ollama URL. The script brings up `docker-compose.test.yml` as project `aepx-test` on ports 8100–8180, exercises identity → trust → registry → gateway → governance → bus → aiplatform → console against the **main stack's Ollama** via `host.docker.internal:11434`, and tears itself down unless you pass `--keep`.

`post.always` runs `docker compose -p aepx-test -f docker-compose.test.yml down -v --remove-orphans || true` as a backstop; the smoke script's own EXIT trap normally tears down first.

**Docker-outside-of-Docker constraint** (Jenkinsfile header): lint and tests run natively in the Jenkins image, because a nested `docker run -v` or `compose up` with relative bind mounts resolves against the host filesystem, not the workspace. The smoke stage does run `compose up` on `docker-compose.test.yml`, whose bind mounts are `./schemas/sql` and `./connectors/catalogue.json`. So it only works when `JENKINS_HOME_MOUNT=/var/jenkins_home`, which puts the workspace at the same path on the host (Linux; on Docker Desktop, share that path or run the smoke test on the host). Keep new stages build-only, or drive containers over HTTP.

## Running Jenkins locally

The full procedure is in `docs/Operational-Manual.html` §10: prerequisites, start, job creation, stage table, troubleshooting and teardown. In short:

```bash
# free RAM first if the main stack is up, e.g. stop some connector categories
export DOCKER_GID=$(stat -c %g /var/run/docker.sock)
sudo mkdir -p /var/jenkins_home && sudo chown 1000:1000 /var/jenkins_home   # Linux, for the smoke stage
export JENKINS_HOME_MOUNT=/var/jenkins_home
docker compose -f docker-compose.jenkins.yml up -d --build
docker compose -f docker-compose.jenkins.yml exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
# UI: http://localhost:8090 — "Select plugins to install" → None (preinstalled), then create a real admin user
```

Then create a **Multibranch Pipeline**: Branch Source GitHub `https://github.com/aliabdalla-maker/aepx-core`, script path `Jenkinsfile`, and periodic scan (1h). Use polling, not webhooks, because Jenkins must not be exposed. A public repo needs no credential. For a private fork, add a read-only fine-grained token as a *Username with password* credential. The smoke stage needs the main stack's Ollama running and warm on host port 11434.

Common failures: `permission denied … docker.sock` means `DOCKER_GID` is wrong. The bus or aiplatform exiting, or Postgres starting with no schema, in the smoke stage means `JENKINS_HOME_MOUNT` is unset. Ports 8100–8180 already in use means a leftover `aepx-test` project, so run `docker compose -p aepx-test -f docker-compose.test.yml down -v`.

These Jenkins settings have not been verified against a live Jenkins yet. If a step fails, fix both the manual and this skill.

**Security:** the socket mount gives Jenkins root-equivalent control of the host. Set an admin password and never expose port 8090 outside a trusted network.

## Jenkins vs GitHub Actions

| | GitHub Actions `ci.yml` | Jenkinsfile |
|---|---|---|
| Trigger | every push and pull_request | whatever the Jenkins job is configured with |
| Components | `test`: 18 services; `test-soa`: bus, 11 connector categories, `sdk/python`, 3 platform apps, `console` | the same 18 services, bus, 11 categories, `console`, `sdk/python` and all 3 platform apps |
| Contracts | `contracts` job | `Contracts` stage |
| Catalogue check | `catalogue` job | — (run `python scripts/gen_connector_catalogue.py --check` locally) |
| Tool pins | `ruff==0.16.0`, `pytest`, `httpx2`, `fakeredis==2.37.0` | the same |
| Test command | `python -m pytest tests -v` | the same (venv `python -m pytest`) |
| Extra stages | — | image build and the v1 integration smoke test |

GitHub Actions is the source of truth. When you add a component or change a pin in `ci.yml`, make the same change in the Jenkinsfile's `components` list and install line in the same PR — a comment above the list says so.

## Related skills

- `aepx-ci-debug` — GitHub Actions failures
- `aepx-test-component` — running one component's lint and tests the CI way
- `aepx-run-stack` — the main stack whose Ollama the smoke test reuses
- `aepx-new-service` — where to register a new component in both pipelines
