#!/usr/bin/env bash
set -euo pipefail
command -v terraform >/dev/null || { echo "Terraform required" >&2; exit 1; }
cd "$(dirname "$0")"
terraform fmt -check
terraform init -backend=false -input=false
terraform validate
echo "OCI London Terraform validated; no resources provisioned."
