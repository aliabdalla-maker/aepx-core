// Single OIDC configuration shared by the workspace, the redirect callback and the silent-renew page.
import { UserManager, WebStorageStateStore } from "oidc-client-ts";

export const oidcAuthority = process.env.NEXT_PUBLIC_OIDC_AUTHORITY || "";
export const oidcClientId = process.env.NEXT_PUBLIC_OIDC_CLIENT_ID || "";
export const oidcConfigured = Boolean(oidcAuthority && oidcClientId);

let manager: UserManager | null = null;

/** Browser-only singleton. Tokens stay in sessionStorage (cleared when the tab closes). */
export function oidcManager(): UserManager {
  if (typeof window === "undefined") throw new Error("OIDC is browser-only");
  manager ??= new UserManager({
    authority: oidcAuthority,
    client_id: oidcClientId,
    redirect_uri: window.location.origin + "/callback",
    silent_redirect_uri: window.location.origin + "/silent-renew",
    post_logout_redirect_uri: window.location.origin + "/",
    response_type: "code", // authorization code + PKCE
    scope: "openid profile",
    automaticSilentRenew: true,
    accessTokenExpiringNotificationTimeInSeconds: 120,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });
  return manager;
}

let registration: UserManager | null = null;

/** Same client, but the authorisation request goes to Keycloak's registration page (Keycloak
 *  ignores prompt=create). The callback is handled by oidcManager() as for any sign-in. */
export function oidcRegistrationManager(): UserManager {
  if (typeof window === "undefined") throw new Error("OIDC is browser-only");
  const base = oidcManager().settings;
  registration ??= new UserManager({
    ...base,
    automaticSilentRenew: false,
    metadataSeed: { authorization_endpoint: registrationEndpoint(oidcAuthority) },
  });
  return registration;
}

export function registrationEndpoint(authority: string): string {
  return authority.replace(/\/+$/, "") + "/protocol/openid-connect/registrations";
}
