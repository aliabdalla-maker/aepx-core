# Restricted Docker test pilot

The Docker pilot is dry-run by default and accepts only the existing offline-test allowlist. The image must already exist locally and be specified by an exact `python@sha256:...` digest. Obtain and independently verify the digest before use; do not substitute a tag.

```bash
python scripts/aepx_autonomous_docker_pilot.py --pattern test_aepx_autonomous_checkpoint.py --image 'python@sha256:<verified-64-hex-digest>'
```

Only after reviewing the command, from a **disposable checkout on a dedicated non-production Docker host**, append `--execute`. The image is not pulled automatically.

Restrictions include disabled container networking, a read-only bind mount of the checkout, a read-only root filesystem, dropped capabilities, no-new-privileges, non-root UID, bounded memory/CPU/PIDs, and a small noexec temporary filesystem.

**Limitations:** Docker daemon privileges, malicious image behavior, host kernel vulnerabilities, repository code and bind-mounted file exposure remain risks. A CLI timeout does not guarantee container termination; inspect and clean up lingering containers after timeout. This wrapper is not a fully secured general-purpose agent execution service. Do not mount secrets or Docker sockets. No OpenAI API calls or autonomous code modification are performed.

Next gates: validate CI, pin a reviewed image, add explicit container identity/cleanup and host isolation, establish actual API usage and spend metering, and implement supervised orchestration with resumable checkpoints.
