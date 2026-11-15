#!/bin/bash
# Applies the server's .env to the aepx realm on every deploy, after Keycloak starts:
#  - "Sign in with Google / GitHub" buttons, present only when their OAuth credentials exist;
#  - outgoing mail (SMTP), and "Forgot password?" only when mail can actually be sent;
#  - optional e-mail verification, an authenticator-app (TOTP) policy users may opt into,
#    and brute-force protection.
# Never prints secrets. Secrets reach kcadm on stdin (JSON), not on the command line.
set -euo pipefail
KC=${AEPX_KCADM:-/opt/keycloak/bin/kcadm.sh}
KC_SERVER=${AEPX_KC_SERVER:-http://keycloak:8080}
REALM=${AEPX_KC_REALM:-aepx}
ADMIN_PW="$(cat "${AEPX_KC_ADMIN_PASSWORD_FILE:-/run/ide-secrets/keycloak_admin}")"
tries=0
until $KC config credentials --server "$KC_SERVER" --realm master \
      --user admin --password "$ADMIN_PW" >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -ge 60 ]; then echo "keycloak not reachable after 5 minutes" >&2; exit 1; fi
  echo "waiting for keycloak"; sleep 5
done

json_str() { # JSON string literal for $1 (escapes backslash, quote and control characters)
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\r'/\\r}; s=${s//$'\t'/\\t}
  printf '"%s"' "$s"
}
is_true() { case "${1,,}" in 1|true|yes|on) return 0;; *) return 1;; esac; }

provider() { # alias client_id client_secret trust_email
  local alias=$1 id=$2 secret=$3 trust=$4
  if [ -z "$id" ] || [ -z "$secret" ]; then
    if $KC get "identity-provider/instances/$alias" -r "$REALM" >/dev/null 2>&1; then
      $KC delete "identity-provider/instances/$alias" -r "$REALM" && echo "$alias sign-in removed"
    else
      echo "$alias sign-in not configured (set its client id and secret in .env)"
    fi
    return
  fi
  local body
  body="{\"alias\":\"$alias\",\"providerId\":\"$alias\",\"enabled\":true,\"trustEmail\":$trust,"
  body+="\"config\":{\"clientId\":$(json_str "$id"),\"clientSecret\":$(json_str "$secret"),"
  body+="\"syncMode\":\"IMPORT\",\"defaultScope\":\"openid email profile\"}}"
  if $KC get "identity-provider/instances/$alias" -r "$REALM" >/dev/null 2>&1; then
    printf '%s' "$body" | $KC update "identity-provider/instances/$alias" -r "$REALM" -f -
  else
    printf '%s' "$body" | $KC create identity-provider/instances -r "$REALM" -f - >/dev/null
  fi
  echo "$alias sign-in enabled"
}
# Google only issues verified addresses, so its e-mail can be trusted for account linking.
# GitHub addresses may be unverified: never trust them to link to an existing account.
provider google "${AEPX_GOOGLE_CLIENT_ID:-}" "${AEPX_GOOGLE_CLIENT_SECRET:-}" true
provider github "${AEPX_GITHUB_CLIENT_ID:-}" "${AEPX_GITHUB_CLIENT_SECRET:-}" false

# Outgoing mail. Explicit AEPX_SMTP_* wins; otherwise Resend's SMTP relay when its API key is
# set. A sender address on a domain verified with the provider is required in both cases.
SMTP_FROM=${AEPX_SMTP_FROM:-}
SMTP_HOST=${AEPX_SMTP_HOST:-}
SMTP_PORT=${AEPX_SMTP_PORT:-587}
SMTP_USER=${AEPX_SMTP_USER:-}
SMTP_PASSWORD=${AEPX_SMTP_PASSWORD:-}
SMTP_SSL=false; SMTP_TLS=true
if [ -z "$SMTP_HOST" ] && [ -n "${RESEND_API_KEY:-}" ]; then
  SMTP_HOST=smtp.resend.com; SMTP_PORT=465; SMTP_USER=resend; SMTP_PASSWORD=$RESEND_API_KEY
  SMTP_SSL=true; SMTP_TLS=false
fi
mail_ready=false
if [ -n "$SMTP_HOST" ] && [ -n "$SMTP_FROM" ]; then
  mail_ready=true
  auth=false; [ -n "$SMTP_USER" ] && auth=true
  smtp="{\"host\":$(json_str "$SMTP_HOST"),\"port\":$(json_str "$SMTP_PORT"),"
  smtp+="\"from\":$(json_str "$SMTP_FROM"),\"fromDisplayName\":$(json_str "${AEPX_SMTP_FROM_NAME:-AEP-X}"),"
  smtp+="\"ssl\":\"$SMTP_SSL\",\"starttls\":\"$SMTP_TLS\",\"auth\":\"$auth\""
  [ "$auth" = true ] && smtp+=",\"user\":$(json_str "$SMTP_USER"),\"password\":$(json_str "$SMTP_PASSWORD")"
  smtp+="}"
  printf '{"smtpServer":%s}' "$smtp" | $KC update "realms/$REALM" -f -
  echo "outgoing mail configured ($SMTP_HOST)"
else
  printf '{"smtpServer":{}}' | $KC update "realms/$REALM" -f -
  echo "outgoing mail not configured (set AEPX_SMTP_FROM and AEPX_SMTP_HOST or RESEND_API_KEY)"
fi

# Password reset and e-mail verification both need working mail, so they follow it.
verify=false
if $mail_ready && is_true "${AEPX_VERIFY_EMAIL:-false}"; then verify=true; fi
registration=true
if is_true "${AEPX_REGISTRATION_DISABLED:-false}"; then registration=false; fi
# Password policy for e-mail accounts (Google accounts use Google's own password rules).
# Keep it in step with "Password rules" in web/public/help/aepx-help.md.
POLICY=${AEPX_PASSWORD_POLICY:-"length(12) and maxLength(128) and upperCase(1) and lowerCase(1) and digits(1) and notUsername(undefined) and notEmail(undefined) and passwordHistory(3)"}
printf '{"resetPasswordAllowed":%s,"verifyEmail":%s,"registrationAllowed":%s,"loginWithEmailAllowed":true,"bruteForceProtected":true,"permanentLockout":false,"failureFactor":10,"waitIncrementSeconds":60,"maxFailureWaitSeconds":900,"otpPolicyType":"totp","otpPolicyAlgorithm":"HmacSHA1","otpPolicyDigits":6,"otpPolicyPeriod":30,"otpPolicyLookAheadWindow":1,"passwordPolicy":%s}' \
  "$mail_ready" "$verify" "$registration" "$(json_str "$POLICY")" | $KC update "realms/$REALM" -f -
echo "password policy: $POLICY"
echo "forgot-password $([ "$mail_ready" = true ] && echo enabled || echo disabled); e-mail verification $verify; registration $registration; authenticator-app (TOTP) available"
