#!/usr/bin/env bash
# Opt-in real-image startup smoke test. No workload or provider execution.
set -euo pipefail
if [[ "${1:-}" != "--execute" || $# -ne 1 ]]; then
  echo "Usage: $0 --execute (requires local aepx-offline-pilot:local image)" >&2
  exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if ! command -v docker >/dev/null 2>&1; then
  echo "Docker executable not found" >&2
  exit 2
fi
if ! docker image inspect aepx-offline-pilot:local >/dev/null 2>&1; then
  echo "Local offline pilot image missing; no pull will be attempted" >&2
  exit 2
fi
help_text="$(docker run --rm --pull never \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 512m --cpus 1 --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001 \
  --mount "type=bind,src=$repo_root,dst=/workspace,readonly" \
  --workdir /workspace aepx-offline-pilot:local --help)"
if [[ "$help_text" != *"--checkpoint"* || "$help_text" != *"--execute"* ]]; then
  echo "Supervised runner help output missing expected arguments" >&2
  exit 1
fi
echo "PASS: actual isolated Python Docker entrypoint imports and starts runner help"
