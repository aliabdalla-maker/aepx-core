#!/usr/bin/env bash
# Opt-in real Docker runtime acceptance; no image builds or external network calls.
set -euo pipefail
if [[ "${1:-}" != "--execute" || $# -ne 1 ]]; then
  echo "Usage: $0 --execute (requires prebuilt aepx-offline-pilot:local)" >&2
  exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
docker run --rm --pull never \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 512m --cpus 1 --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001 \
  --mount "type=bind,src=$repo_root,dst=/workspace,readonly" \
  --workdir /workspace --entrypoint python aepx-offline-pilot:local -I -c '
import os, pathlib, socket, sys
assert os.getuid() == 10001 and os.geteuid() == 10001, "wrong uid"
assert not pathlib.Path("/var/run/docker.sock").exists(), "docker socket exposed"
for target in ("/workspace/.aepx-runtime-write-probe", "/aepx-runtime-write-probe"):
    try:
        pathlib.Path(target).write_text("probe")
    except OSError:
        pass
    else:
        pathlib.Path(target).unlink(missing_ok=True)
        raise AssertionError("writable protected path: " + target)
try:
    socket.create_connection(("1.1.1.1", 443), timeout=1)
except OSError:
    pass
else:
    raise AssertionError("network unexpectedly reachable")
print("PASS: uid, socket, filesystem and network probes")
'
