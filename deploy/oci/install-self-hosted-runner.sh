#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/aliabdalla-maker/aepx-core}"
RUNNER_NAME="${RUNNER_NAME:-oci-aepx-$(hostname)}"
RUNNER_LABELS="${RUNNER_LABELS:-oci-aepx}"
RUNNER_HOME="${RUNNER_HOME:-/opt/actions-runner}"
RUNNER_USER="${RUNNER_USER:-${SUDO_USER:-$(id -un)}}"
RUNNER_TOKEN="${RUNNER_TOKEN:-}"

if [[ -z "$RUNNER_TOKEN" ]]; then
  echo "RUNNER_TOKEN is required. Generate a short-lived registration token from:"
  echo "https://github.com/aliabdalla-maker/aepx-core/settings/actions/runners/new"
  exit 2
fi

arch="$(uname -m)"
case "$arch" in
  x86_64) runner_arch="x64" ;;
  aarch64|arm64) runner_arch="arm64" ;;
  *) echo "Unsupported architecture: $arch"; exit 3 ;;
esac

sudo apt-get update
sudo apt-get install -y curl jq rsync nginx ca-certificates tar

release_json="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest)"
version="$(jq -r '.tag_name' <<<"$release_json")"
version_num="${version#v}"
asset="actions-runner-linux-${runner_arch}-${version_num}.tar.gz"
url="https://github.com/actions/runner/releases/download/${version}/${asset}"

sudo mkdir -p "$RUNNER_HOME"
sudo chown "$RUNNER_USER":"$RUNNER_USER" "$RUNNER_HOME"
cd "$RUNNER_HOME"

if [[ ! -x ./config.sh ]]; then
  curl -fL "$url" -o "$asset"
  tar xzf "$asset"
  rm -f "$asset"
fi

if [[ -f .runner ]]; then
  echo "Runner is already configured at $RUNNER_HOME"
else
  sudo -u "$RUNNER_USER" ./config.sh \
    --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$RUNNER_LABELS" \
    --unattended \
    --replace
fi

sudo ./svc.sh install "$RUNNER_USER" || true
sudo ./svc.sh start
sudo ./svc.sh status

echo "Self-hosted runner configured with label: $RUNNER_LABELS"
echo "Next: install deploy/oci/nginx-aepx-location.conf in the active HTTPS server block and test nginx."
