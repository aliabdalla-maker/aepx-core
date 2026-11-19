#!/usr/bin/env bash
# Prepare a host to run AEP-X user code in gVisor sandboxes. Run as root on Ubuntu 22.04/24.04.
#
#   Dedicated VM (recommended):  IDE_SERVER_IP=10.0.0.12 RUNNER_SHARED_SECRET=... ./setup-runner-host.sh dedicated
#   Same host as the IDE:        ./setup-runner-host.sh same-host     (then enable the "sandbox" compose profile)
#
# Dedicated mode also builds and starts the runner on port 8080 of the VM's private address and
# allows that port only from IDE_SERVER_IP. The script ends with a self-test that proves runs
# use gVisor and have no network. It is safe to re-run.
set -euo pipefail
MODE=${1:-dedicated}
REF=${AEPX_RUNNER_REF:-master}
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

echo "== Docker"
if ! command -v docker >/dev/null; then
  apt-get update -qq && apt-get install -y -qq docker.io ca-certificates curl gnupg git
  systemctl enable --now docker
fi

echo "== gVisor (runsc)"
if ! command -v runsc >/dev/null; then
  curl -fsSL https://gvisor.dev/archive.key | gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
    > /etc/apt/sources.list.d/gvisor.list
  apt-get update -qq && apt-get install -y -qq runsc
fi
runsc install            # registers the "runsc" runtime in /etc/docker/daemon.json
systemctl restart docker

echo "== Sandbox images"
docker pull -q python:3.12-alpine
docker pull -q node:22-alpine
mkdir -p /var/aepx-runs && chmod 711 /var/aepx-runs

echo "== Self-test"
out=$(docker run --rm --runtime runsc --network none --read-only --user 65534:65534 python:3.12-alpine \
  python3 -c "import platform,socket
print('kernel', platform.release())
try:
    socket.create_connection(('1.1.1.1', 53), timeout=2); print('NETWORK OPEN')
except OSError:
    print('network blocked')")
echo "$out"
echo "$out" | grep -q "network blocked" || { echo "SELF-TEST FAILED: sandbox has network" >&2; exit 1; }
# gVisor reports its own (fixed) kernel version rather than the host's.
[ "$(echo "$out" | awk '/kernel/{print $2}')" != "$(uname -r)" ] || { echo "SELF-TEST FAILED: not running under gVisor" >&2; exit 1; }
echo "gVisor sandbox OK"

if [ "$MODE" = same-host ]; then
  echo "Done. Now set AEPX_IDE_RUNNER_SECRET in the IDE .env and start the compose profile 'sandbox'."
  exit 0
fi

echo "== Runner service (dedicated)"
: "${IDE_SERVER_IP:?set IDE_SERVER_IP to the private IP of the IDE server}"
: "${RUNNER_SHARED_SECRET:?set RUNNER_SHARED_SECRET (32+ random characters, same value as IDE_RUNNER_SECRET on the IDE)}"
[ ${#RUNNER_SHARED_SECRET} -ge 32 ] || { echo "RUNNER_SHARED_SECRET must be at least 32 characters" >&2; exit 1; }
BIND_IP=${RUNNER_BIND_IP:-$(hostname -I | awk '{print $1}')}
src=/opt/aepx-core
if [ -d $src/.git ]; then git -C $src fetch -q origin && git -C $src checkout -q "$REF" && git -C $src pull -q --ff-only || true
else git clone -q https://github.com/aliabdalla-maker/aepx-core.git $src && git -C $src checkout -q "$REF"; fi
docker build -q -t aepx-runner $src/platform/saas-ide/runner
docker rm -f aepx-runner >/dev/null 2>&1 || true
umask 077; printf 'RUNNER_SHARED_SECRET=%s\n' "$RUNNER_SHARED_SECRET" > /etc/aepx-runner.env
docker run -d --name aepx-runner --restart unless-stopped \
  -p "$BIND_IP:8080:8080" --env-file /etc/aepx-runner.env \
  -e RUNNER_RUNTIME=runsc -e RUNNER_WORK_ROOT=/var/aepx-runs -e RUNNER_MAX_CONCURRENT=2 \
  -v /var/run/docker.sock:/var/run/docker.sock -v /var/aepx-runs:/var/aepx-runs aepx-runner >/dev/null

echo "== Firewall: port 8080 only from $IDE_SERVER_IP"
iptables -C DOCKER-USER -p tcp --dport 8080 ! -s "$IDE_SERVER_IP" -j DROP 2>/dev/null \
  || iptables -I DOCKER-USER -p tcp --dport 8080 ! -s "$IDE_SERVER_IP" -j DROP
sleep 3
curl -fsS "http://$BIND_IP:8080/health" && echo
echo "Done. On the IDE server set: IDE_RUNNER_URL=http://$BIND_IP:8080 IDE_RUNNER_ALLOW_PRIVATE_HTTP=true"
echo "IDE_RUNNER_SECRET=<same secret> and, after the acceptance checks, IDE_CODE_EXECUTION_ENABLED=true."
echo "Also restrict TCP 8080 to the IDE server in the OCI security list."
