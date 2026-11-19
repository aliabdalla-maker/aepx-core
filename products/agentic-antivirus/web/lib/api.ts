// Control-plane client. Session token and tenant live in sessionStorage (cleared with the tab);
// storage access is wrapped because it can throw in privacy modes and embedded shells.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

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
    return JSON.stringify(e.detail);
  }
  return "The server could not be reached. Check your connection and try again.";
}
