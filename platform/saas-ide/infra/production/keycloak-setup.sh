#!/bin/bash
# Turns on "Sign in with Google" and "Sign in with GitHub" in the aepx realm when their
# OAuth client ids are present in the server's .env; removes a button whose credentials
# were taken away. Runs after Keycloak starts, on every deploy. Never prints secrets.
set -euo pipefail
KC=/opt/keycloak/bin/kcadm.sh
ADMIN_PW="$(cat /run/ide-secrets/keycloak_admin)"
until $KC config credentials --server http://keycloak:8080 --realm master \
      --user admin --password "$ADMIN_PW" >/dev/null 2>&1; do
  echo "waiting for keycloak"; sleep 5
done

provider() { # alias client_id client_secret
  local alias=$1 id=$2 secret=$3
  if [ -z "$id" ] || [ -z "$secret" ]; then
    if $KC get "identity-provider/instances/$alias" -r aepx >/dev/null 2>&1; then
      $KC delete "identity-provider/instances/$alias" -r aepx && echo "$alias sign-in removed"
    else
      echo "$alias sign-in not configured (set its client id and secret in .env)"
    fi
    return
  fi
  local args=(-s "alias=$alias" -s "providerId=$alias" -s enabled=true -s trustEmail=true
              -s "config.clientId=$id" -s "config.clientSecret=$secret" -s config.syncMode=IMPORT)
  if $KC get "identity-provider/instances/$alias" -r aepx >/dev/null 2>&1; then
    $KC update "identity-provider/instances/$alias" -r aepx "${args[@]}"
  else
    $KC create identity-provider/instances -r aepx "${args[@]}"
  fi
  echo "$alias sign-in enabled"
}
provider google "${AEPX_GOOGLE_CLIENT_ID:-}" "${AEPX_GOOGLE_CLIENT_SECRET:-}"
provider github "${AEPX_GITHUB_CLIENT_ID:-}" "${AEPX_GITHUB_CLIENT_SECRET:-}"
