#!/usr/bin/env bash
set -Eeuo pipefail
# Read-only local image platform inspection. No pull/build/run.
cd "$(dirname "$0")/../.."
command -v docker >/dev/null
command -v python3 >/dev/null
ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) PLATFORM="linux/arm64";;
  x86_64|amd64) PLATFORM="linux/amd64";;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 2;;
esac
echo "Target platform: $PLATFORM"
docker compose -f docker-compose.yml config --format json | python3 -c '
import json,sys
cfg=json.load(sys.stdin)
for name,s in cfg["services"].items():
    print(name, "image="+s.get("image","<build required>"), "platform="+s.get("platform","auto"))
'
echo "This is an inventory only. Verify each upstream image manifest and build on target architecture before deployment."
