#!/usr/bin/env bash
# Explicitly opt-in, network-disabled, non-root offline test execution.
set -euo pipefail
if [[ "${1:-}" != "--execute" ]]; then
  echo "Dry run only. Usage: $0 --execute <absolute-checkpoint-dir> <allowlisted-pattern> [count]" >&2
  exit 2
fi
if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "Expected checkpoint directory, pattern and optional count" >&2
  exit 2
fi
checkpoint_dir="$2"
pattern="$3"
count="${4:-1}"
case "$checkpoint_dir" in /*) ;; *) echo "Checkpoint directory must be absolute" >&2; exit 2;; esac
if [[ ! -d "$checkpoint_dir" || -L "$checkpoint_dir" ]]; then
  echo "Checkpoint directory must exist and not be a symlink" >&2; exit 2
fi
case "$count" in ''|*[!0-9]*) echo "Count must be an integer" >&2; exit 2;; esac
if (( 10#$count < 1 || 10#$count > 100 )); then
  echo "Count must be 1..100" >&2; exit 2
fi
case "$pattern" in
  test_aepx_autonomous_checkpoint.py|test_aepx_pilot_checkpoint.py|test_aepx_supervised_batch.py|test_aepx_budget_admission.py|test_aepx_budget_ledger.py) ;;
  *) echo "Pattern not approved by launcher" >&2; exit 2 ;;
esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
checkpoint_dir="$(cd "$checkpoint_dir" && pwd -P)"
if [[ "$checkpoint_dir" == "$repo_root" || "$checkpoint_dir" == "$repo_root/"* ]]; then
  echo "Checkpoint directory must be outside source tree" >&2
  exit 2
fi
if [[ ! -w "$checkpoint_dir" ]]; then
  echo "Checkpoint directory must be writable" >&2; exit 2
fi
docker run --rm \
  --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 512m --cpus 1 \
  --user 10001:10001 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001 \
  --mount "type=bind,src=$repo_root,dst=/workspace,readonly" \
  --mount "type=bind,src=$checkpoint_dir,dst=/checkpoint" \
  --workdir /workspace \
  aepx-offline-pilot:local \
  --repo /workspace --checkpoint /checkpoint/pilot.json \
  --pattern "$pattern" --count "$count" --timeout 60 --max-seconds 600 --execute
