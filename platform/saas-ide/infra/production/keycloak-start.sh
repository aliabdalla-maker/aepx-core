#!/bin/bash
# Reads the database and first-admin passwords from the generated secrets volume.
set -euo pipefail
export KC_DB_PASSWORD="$(cat /run/ide-secrets/keycloak_db)"
export KC_BOOTSTRAP_ADMIN_USERNAME=admin
export KC_BOOTSTRAP_ADMIN_PASSWORD="$(cat /run/ide-secrets/keycloak_admin)"
exec /opt/keycloak/bin/kc.sh start --optimized --import-realm "$@"
