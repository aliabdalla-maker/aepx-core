// Sign-in options, account links and honest panel states. Pure helpers (unit-tested); the only
// network call is fetchAuthOptions, which reads the API's public flags.

export type AuthOptions = { google: boolean; github: boolean; password_reset: boolean; registration: boolean; mfa: boolean };

/** Safe default when the API cannot be reached: only plain e-mail sign-in, which always exists. */
export const DEFAULT_AUTH_OPTIONS: AuthOptions = { google: false, github: false, password_reset: false, registration: true, mfa: false };

export function parseAuthOptions(raw: unknown): AuthOptions {
  if (!raw || typeof raw !== "object") return DEFAULT_AUTH_OPTIONS;
  const r = raw as Record<string, unknown>;
  const flag = (k: keyof AuthOptions) => (typeof r[k] === "boolean" ? (r[k] as boolean) : DEFAULT_AUTH_OPTIONS[k]);
  return { google: flag("google"), github: flag("github"), password_reset: flag("password_reset"), registration: flag("registration"), mfa: flag("mfa") };
}

export async function fetchAuthOptions(apiBase: string, fetcher: typeof fetch = fetch): Promise<AuthOptions> {
  try {
    const r = await fetcher(apiBase + "/api/v1/auth-options", { credentials: "omit" });
    return r.ok ? parseAuthOptions(await r.json()) : DEFAULT_AUTH_OPTIONS;
  } catch { return DEFAULT_AUTH_OPTIONS; }
}

/** Keycloak's own "Forgot your password?" page for this client (works without a login session). */
export function forgotPasswordUrl(authority: string, clientId: string): string {
  return authority.replace(/\/+$/, "") + "/login-actions/reset-credentials?client_id=" + encodeURIComponent(clientId);
}

export type AccountSection = "personal-info" | "signing-in" | "linked-accounts" | "device-activity";
const ACCOUNT_PATHS: Record<AccountSection, string> = {
  "personal-info": "#/personal-info",
  "signing-in": "#/security/signingin",
  "linked-accounts": "#/security/linked-accounts",
  "device-activity": "#/security/device-activity",
};
/** Keycloak Account Console pages: profile, password + authenticator app, Google/GitHub links, sessions. */
export function accountUrl(authority: string, section: AccountSection): string {
  return authority.replace(/\/+$/, "") + "/account/" + ACCOUNT_PATHS[section];
}

/** Extra authorisation-request parameters for each sign-in button. */
export function signinArgs(kind: "email" | "create" | "google" | "github"): { prompt?: string; extraQueryParams?: Record<string, string> } {
  if (kind === "create") return {}; // sent to the registrations endpoint instead (see auth.ts)
  if (kind === "google" || kind === "github") return { extraQueryParams: { kc_idp_hint: kind } };
  return {};
}

/** What a data panel should say, so "no data" is never shown when the real cause is different. */
export type PanelState = "signed-out" | "loading" | "denied" | "unavailable" | "failed" | "empty" | "ready";
export function panelStateFromError(e: unknown): PanelState {
  const status = typeof e === "object" && e && "status" in e ? Number((e as { status: unknown }).status) : NaN;
  if (status === 401 || status === 403) return "denied";
  if (status === 404 || status === 502 || status === 503 || status === 504 || Number.isNaN(status)) return "unavailable";
  return "failed";
}
export const PANEL_TEXT: Record<PanelState, string> = {
  "signed-out": "Sign in to see operations.",
  loading: "Loading…",
  denied: "Only workspace owners and administrators can see operations.",
  unavailable: "Operations service is unreachable right now. Try again shortly.",
  failed: "Operations could not be loaded. Try again; if it persists, report it.",
  empty: "No MCP executions recorded yet.",
  ready: "",
};

/** Why Save is disabled — shown as the button's tooltip and accessible description. */
export function saveHint(o: { signedIn: boolean; hasFile: boolean; dirty: boolean }): string {
  if (!o.signedIn) return "Sign in and open a project to save files.";
  if (!o.hasFile) return "Open a file to save it.";
  if (!o.dirty) return "No unsaved changes.";
  return "Save this file (Ctrl/⌘+S).";
}

/** Short release label for the status bar; flags a web/API mismatch so stale deploys are visible. */
export function releaseLabel(web: string | undefined, api: string | null | undefined): { text: string; drift: boolean } {
  const short = (s?: string | null) => (s && /^[0-9a-f]{7,40}$/i.test(s) ? s.slice(0, 7).toLowerCase() : "");
  const w = short(web), a = short(api);
  if (!w && !a) return { text: "", drift: false };
  if (w && a && w !== a) return { text: `web ${w} · api ${a}`, drift: true };
  return { text: `build ${w || a}`, drift: false };
}
