// Control-plane client. Session token and tenant live in sessionStorage (cleared with the tab);
// storage access is wrapped because it can throw in privacy modes and embedded shells.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

/** Absolute control-plane address, for agents enrolling against this console. */
export function apiUrl(): string {
  return new URL(API_BASE, typeof location === "undefined" ? "https://localhost" : location.origin).href.replace(/\/$/, "");
}

const TOKEN = "aav.token";
const TENANT = "aav.tenant";

function store(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}

export const session = {
  token: () => store()?.getItem(TOKEN) ?? null,
  tenant: () => store()?.getItem(TENANT) ?? null,
  set(token: string, tenant?: string) {
    try {
      store()?.setItem(TOKEN, token);
      if (tenant) store()?.setItem(TENANT, tenant);
    } catch { /* storage unavailable: session lasts for this page only */ }
  },
  setTenant(tenant: string) {
    try { store()?.setItem(TENANT, tenant); } catch { /* ignore */ }
  },
  clear() {
    try { store()?.removeItem(TOKEN); store()?.removeItem(TENANT); } catch { /* ignore */ }
  },
};

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}

type Opts = { method?: string; body?: unknown; form?: FormData; query?: Record<string, string | number | boolean | undefined> };

export async function api<T = any>(path: string, opts: Opts = {}, fetcher: typeof fetch = fetch): Promise<T> {
  const headers: Record<string, string> = {};
  const t = session.token();
  const tenant = session.tenant();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (tenant) headers["X-Tenant-Id"] = tenant;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const qs = opts.query
    ? "?" + new URLSearchParams(Object.entries(opts.query).filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)])).toString()
    : "";
  const res = await fetcher(`${API_BASE}${path}${qs}`, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new ApiError(res.status, (data as any)?.detail ?? data);
  return data as T;
}

export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return "Your session has ended. Sign in again.";
    if (e.status === 402) return "Your trial has ended. Subscribe to keep using the console.";
    if (e.status === 403 && e.detail === "email not verified")
      return "Confirm your email address first: open the link we sent you, or sign out and sign in again to get a new link.";
    if (e.status === 403) return typeof e.detail === "string" ? `Not allowed: ${e.detail}` : "You do not have permission for this.";
    if (typeof e.detail === "string") return e.detail;
    if (Array.isArray(e.detail)) return describeValidation(e.detail);
    if (e.detail && typeof e.detail === "object" && typeof (e.detail as any).error === "string")
      return (e.detail as any).error;
    return `The request was refused (HTTP ${e.status}).`;
  }
  return "The server could not be reached. Check your connection and try again.";
}

const FIELD_NAMES: Record<string, string> = {
  artefact_digest: "Version or digest", evidence: "Evidence", reason: "Reason", device_ids: "Devices",
  name: "Name", endpoint: "Endpoint", secret_ref: "Secret reference", cron: "Schedule", value: "Value",
  allowed_management_hosts: "Management hosts", email: "Email", password: "Password",
};

/** FastAPI/pydantic validation errors (422) as one readable sentence per field, never raw JSON. */
export function describeValidation(items: unknown[]): string {
  const lines = items.map((it: any) => {
    const field = Array.isArray(it?.loc) ? String(it.loc[it.loc.length - 1]) : "";
    const label = FIELD_NAMES[field] ?? field.replace(/_/g, " ");
    const ctx = it?.ctx ?? {};
    switch (it?.type) {
      case "string_too_short": return `${label}: enter at least ${ctx.min_length} characters.`;
      case "string_too_long": return `${label}: use at most ${ctx.max_length} characters.`;
      case "too_short": return `${label}: choose at least ${ctx.min_length}.`;
      case "missing": return `${label} is required.`;
      case "string_pattern_mismatch": return `${label} is not in the expected format.`;
      default: return `${label}: ${String(it?.msg ?? "invalid value").replace(/^Value error, /, "")}.`;
    }
  });
  return lines.length ? lines.join(" ") : "Some values are not valid.";
}
