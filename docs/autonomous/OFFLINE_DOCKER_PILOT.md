# Offline Docker pilot (opt-in)

This is a supervised **unit-test** runner, not an LLM engineering agent. It must never be used as a production isolation guarantee without runtime security review.

On a trusted Linux Docker host, build the image explicitly (image build may need network access):

```bash
docker build -f docker/offline-pilot/Dockerfile -t aepx-offline-pilot:local .
mkdir -p /tmp/aepx-pilot-checkpoints
sudo chown 10001:10001 /tmp/aepx-pilot-checkpoints
bash scripts/run_aepx_offline_docker.sh --execute /tmp/aepx-pilot-checkpoints test_aepx_autonomous_checkpoint.py 1
```

The launcher requires explicit opt-in and an absolute checkpoint directory outside the source tree. It mounts source read-only, checkpoint directory writable, disables container networking, removes Linux capabilities, prevents privilege escalation, uses a read-only root filesystem and a bounded temporary filesystem, and caps memory/CPU/processes. It does not mount the Docker socket or forward secrets.

**Limitations:** A malicious test may still exploit kernel/runtime vulnerabilities; Docker host, daemon and image supply chain must be trusted. Runtime tests have not been executed in CI. The image includes only Python stdlib; dependency-heavy allowlisted tests may fail until a reviewed, pinned offline dependency image is supplied. The checkpoint directory is writable by UID 10001 and must be dedicated to this runner. A Docker CLI or daemon failure is not evidence of successful isolation. Do not run against production credentials or paid provider services.

## Launcher command contract tests

Run `python -m unittest discover -s tests -p 'test_aepx_docker_launcher_contract.py' -v` on a Linux runner with Bash and Python. The tests replace the Docker CLI with a temporary fake executable and inspect the actual argument vector. They verify isolation flags, source/checkpoint mount permissions, and rejection before invocation for unsafe inputs. They **do not** create containers or establish runtime isolation; a separate disposable Docker integration test is still required.

## Explicit real-container acceptance

After reviewing and building the local image on a disposable Linux Docker host, run:

```bash
bash scripts/test_aepx_offline_docker_runtime.sh --execute
```

The test uses the local image only (`--pull never`) and probes the effective UID, absent Docker socket, read-only source/root filesystem, and blocked outbound TCP. A failed probe exits nonzero. The supervised launcher also now forbids implicit image pulls. This is **not** a penetration test or proof of a complete security boundary; verify kernel isolation, mount semantics, dependency supply chain and a pinned image digest before production use. This acceptance script is deliberately **not** automatically run by CI.

## Checkpoint mount runtime acceptance

The container must also demonstrate non-root checkpoint persistence, not just deny unsafe writes. On a **disposable trusted Linux Docker host**, create a dedicated directory outside the source tree owned by UID/GID 10001 and run:

```bash
mkdir -p /tmp/aepx-pilot-checkpoints
sudo chown 10001:10001 /tmp/aepx-pilot-checkpoints
bash scripts/test_aepx_docker_checkpoint_runtime.sh --execute /tmp/aepx-pilot-checkpoints
```

The probe writes a temporary checkpoint file as UID 10001, flushes and fsyncs it, reads it back and removes it. It never runs the supervised test batch or makes provider calls. Failure indicates an unusable checkpoint mount; do not bypass it by running the application as root or granting broad filesystem permissions. The probe is opt-in and not automatically invoked by CI.

## Isolated Python runner import fix

The image uses `python -I -c` and explicitly inserts `/workspace/scripts` into `sys.path` before importing `aepx_supervised_batch.main()`. This avoids the sibling-module import failure caused by directly executing `/workspace/scripts/aepx_supervised_batch.py` with `-I`, which omits its script directory from Python's import path. The added offline regression test exercises the import pattern with `--help`; the real Docker image still needs a runtime acceptance check. Only the mounted repository scripts are added to the import path, so this is not a substitute for reviewing untrusted repository code.
