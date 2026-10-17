#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/aliabdalla-maker/aepx-core}"
RUNNER_NAME="${RUNNER_NAME:-oci-aepx-$(hostname)}"
RUNNER_HOME="${RUNNER_HOME:-/opt/actions-runner}"
RUNNER_USER="${RUNNER_USER:-${SUDO_USER:-$(id -un)}}"
RUNNER_TOKEN="${RUNNER_TOKEN:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$RUNNER_TOKEN" ]]; then
  echo "RUNNER_TOKEN is required. Generate a fresh short-lived token from:"
  echo "https://github.com/aliabdalla-maker/aepx-core/settings/actions/runners/new?arch=x64&os=linux"
  exit 2
fi

arch="$(uname -m)"
case "$arch" in
  x86_64) runner_arch="x64" ;;
  aarch64|arm64) runner_arch="arm64" ;;
  *) echo "Unsupported architecture: $arch"; exit 3 ;;
esac

sudo apt-get update
sudo apt-get install -y curl jq rsync ca-certificates tar

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
    --unattended \
    --replace
fi

# Install a root-owned, constrained deployment helper. The Actions job is not
# granted general passwordless sudo; it can invoke only this audited command.
sudo install -o root -g root -m 0755 \
  "$SCRIPT_DIR/deploy-aepx-root.sh" /usr/local/sbin/deploy-aepx

sudo install -d -m 0755 /srv/aepx/releases
sudoers_file="/etc/sudoers.d/aepx-github-runner"
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/deploy-aepx *\n' "$RUNNER_USER" \
  | sudo tee "$sudoers_file" >/dev/null
sudo chmod 0440 "$sudoers_file"
sudo visudo -cf "$sudoers_file"

sudo ./svc.sh install "$RUNNER_USER" || true
sudo ./svc.sh start
sudo ./svc.sh status

echo "Self-hosted runner configured with GitHub default labels."
echo "Privileged deployment is restricted to /usr/local/sbin/deploy-aepx."
echo "Caddy integration is maintained in aliabdalla-maker/good-hour."
