#!/usr/bin/env bash
# Opt-in real Docker checkpoint mount acceptance. Does not execute project tests.
set -euo pipefail
if [[ "${1:-}" != "--execute" || $# -ne 2 ]]; then
  echo "Usage: $0 --execute <absolute-dedicated-checkpoint-directory>" >&2
  exit 2
fi
checkpoint_dir="$2"
case "$checkpoint_dir" in /*) ;; *) echo "Absolute directory required" >&2; exit 2;; esac
if [[ ! -d "$checkpoint_dir" || -L "$checkpoint_dir" ]]; then
  echo "Directory missing or symlinked" >&2; exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
checkpoint_dir="$(cd "$checkpoint_dir" && pwd -P)"
if [[ "$checkpoint_dir" == "$repo_root" || "$checkpoint_dir" == "$repo_root/"* ]]; then
  echo "Checkpoint directory must be outside repository" >&2; exit 2
fi
if [[ ! -w "$checkpoint_dir" ]]; then
  echo "Checkpoint directory must be writable by caller" >&2; exit 2
fi
docker run --rm --pull never \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 512m --cpus 1 --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001 \
  --mount "type=bind,src=$repo_root,dst=/workspace,readonly" \
  --mount "type=bind,src=$checkpoint_dir,dst=/checkpoint" \
  --workdir /workspace --entrypoint python aepx-offline-pilot:local -I -c '
import os, pathlib, tempfile
checkpoint = pathlib.Path("/checkpoint")
assert os.geteuid() == 10001
fd, name = tempfile.mkstemp(prefix=".aepx-acceptance-", dir=checkpoint)
try:
    with os.fdopen(fd, "w") as stream:
        stream.write("checkpoint-write-ok")
        stream.flush()
        os.fsync(stream.fileno())
    assert pathlib.Path(name).read_text() == "checkpoint-write-ok"
finally:
    pathlib.Path(name).unlink(missing_ok=True)
print("PASS: non-root checkpoint write, fsync, read and cleanup")
'
