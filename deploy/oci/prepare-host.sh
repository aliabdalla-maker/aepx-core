#!/usr/bin/env bash
set -Eeuo pipefail
# Run on an Ubuntu OCI Ampere A1 VM as a sudo-capable user.
if [[ $(id -u) -ne 0 ]]; then echo "Run: sudo bash deploy/oci/prepare-host.sh"; exit 1; fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git ufw openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
# Keep SSH accessible; OCI security lists must also allow SSH.
ufw allow 22/tcp
ufw --force enable
mkdir -p /opt/aepx
chmod 750 /opt/aepx
echo "Docker installed. Only SSH allowed by host firewall."
echo "Do not expose ports 8000-8031, 5432, 6379, 9092, 7474, 7687, or 11434."
