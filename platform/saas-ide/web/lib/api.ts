// Typed client for the AEP-X IDE backend (platform/saas-ide/backend/app/main.py).
// Every call is tenant-scoped by the X-Tenant-ID header and authorised by the OIDC bearer token;
// the backend re-verifies membership and role, so nothing here is a security boundary.

export type Project = { id: string; name: string; description: string; module?: string };
export type IdeModule = {
  id: string; name: string; summary: string; status: "available" | "planned" | string;
  crew: { agent: string; goal: string }[]; starter_files: Record<string, string>; quick_tasks: string[];
};
export type FileVersion = { version: number; op: "save" | "delete" | "restore" | string; author: string; created_at: string; size: number };
export type Member = { subject: string; role: string };
export type AuditEvent = { id: number; actor: string; action: string; resource_type: string; resource_id: string; detail: string; hash: string; created_at: string };
export const MEMBER_ROLES = ["owner", "admin", "editor", "media_editor", "reviewer", "viewer"] as const;
export type FileEntry = { path: string; content: string };
export type RunStatus =
  | "awaiting_approval" | "approved" | "rejected" | "running" | "succeeded"
  | "failed" | "cancelled" | string;
export type RunSummary = {
  id: string; status: RunStatus; model_route: string; task: string; attempts: number; result: string;
};
export type RunDetail = {
  id: string; status: RunStatus; model_route: string; plan: unknown; result?: string;
};
export type AuditEntry = { actor: string; action: string };
export type ToolApproval = {
  id: string; server: string; tool: string; args_sha256: string; state: string;
  requested_by: string; decided_by: string | null;
};
export type Capabilities = {
  providers: Record<string, boolean>;
  crewai_execution_enabled: boolean;
  mcp_allowlisted_servers: string[];
  mcp_execution_enabled: boolean;
  knowledge_retrieval: string;
  approval_required: boolean;
  /** True when the isolated agent worker is deployed and paid AI is switched on. */
  agents_live?: boolean;
};
export type AiUsage = {
  plan: "free" | "trial" | "pro" | string;
  agents_live: boolean;
  used_today_microusd: number;
  daily_allowance_microusd: number;
  used_today_percent: number;
  platform_budget_available: boolean;
};
export type LexicalMatch = { id: string; title: string; excerpt: string; score: number };
export type VectorMatch = { document_id: string; excerpt: string; score: number };
export type Provider = "oci" | "openai" | "anthropic" | "gemini" | "openrouter";
export type Entitlement = {
  plan: "trial" | "pro" | "free"; ad_rate: number; subscribed: boolean; trial_days_left: number;
  trial_ends_at: string; renews_at: string | null; will_renew: boolean; price: string;
  account_id: string; source: string | null; can_manage_on_web: boolean;
};

export type Requester = <T = unknown>(url: string, method?: string, body?: unknown) => Promise<T>;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Builds a requester bound to one API base, token and tenant. */
export function makeRequester(base: string, token: string, tenant: string,
                              fetchImpl: typeof fetch = fetch): Requester {
  return async <T,>(url: string, method = "GET", body?: unknown): Promise<T> => {
    if (!token) throw new ApiError(401, "Sign in first");
    const response = await fetchImpl(base + url, {
      method,
      headers: {
        Authorization: "Bearer " + token,
        "X-Tenant-ID": tenant,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = "";
      try { const data = await response.json(); detail = typeof data?.detail === "string" ? data.detail : ""; }
      catch { /* non-JSON error body */ }
      throw new ApiError(response.status, detail ? `${response.status}: ${detail}` : `API error ${response.status}`);
    }
    return (response.status === 204 ? undefined : await response.json()) as T;
  };
}

/** Authenticated binary download (generated media previews); returns an object URL the caller must revoke. */
export function makeBlobFetcher(base: string, token: string, tenant: string, fetchImpl: typeof fetch = fetch) {
  return async (url: string): Promise<{ objectUrl: string; type: string }> => {
    if (!token) throw new ApiError(401, "Sign in first");
    const response = await fetchImpl(base + url, {
      headers: { Authorization: "Bearer " + token, "X-Tenant-ID": tenant }, cache: "no-store" });
    if (!response.ok) throw new ApiError(response.status, `API error ${response.status}`);
    const blob = await response.blob();
    return { objectUrl: URL.createObjectURL(blob), type: blob.type };
  };
}

/** Encodes a validated relative workspace path segment by segment. */
export function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

/** Mirrors backend safe_path(): relative, no empty/dot segments, no backslashes or NUL. */
export function isSafeRelativePath(path: string): boolean {
  if (!path || path.length > 512 || path.startsWith("/") || path.includes("\\") || path.includes("\0")) return false;
  return path.split("/").every(part => part !== "" && part !== "." && part !== "..");
}

export const ideApi = (r: Requester) => ({
  me: () => r<{ subject: string; tenant_id: string; role: string }>("/api/v1/me"),
  entitlement: () => r<Entitlement>("/api/v1/entitlement"),
  stripeCheckout: () => r<{ url: string }>("/api/v1/billing/stripe/checkout", "POST"),
  stripePortal: () => r<{ url: string }>("/api/v1/billing/stripe/portal", "POST"),
  appStoreVerify: (originalTransactionId: string, bundleId?: string) =>
    r<Entitlement>("/api/v1/billing/app-store/verify", "POST",
      { original_transaction_id: originalTransactionId, ...(bundleId ? { bundle_id: bundleId } : {}) }),
  capabilities: () => r<Capabilities>("/api/v1/agent-capabilities"),
  aiUsage: () => r<AiUsage>("/api/v1/ai-usage"),
  executionStatus: () => r<import("./run").ExecutionStatus>("/api/v1/execution"),
  runFile: (project: string, entry: string, stdin = "") =>
    r<import("./run").RunOutput>(`/api/v1/projects/${encodeURIComponent(project)}/run`, "POST", { entry, stdin }),
  projects: () => r<Project[]>("/api/v1/projects"),
  createProject: (name: string, description = "", module = "software") =>
    r<Project>("/api/v1/projects", "POST", { name, description, module }),
  modules: () => r<IdeModule[]>("/api/v1/ide-modules"),
  updateProject: (id: string, changes: { name?: string; description?: string }) =>
    r<Project>(`/api/v1/projects/${encodeURIComponent(id)}`, "PATCH", changes),
  archiveProject: (id: string) => r(`/api/v1/projects/${encodeURIComponent(id)}`, "DELETE"),
  archivedProjects: () => r<(Project & { archived_at: string })[]>("/api/v1/projects-archived"),
  restoreProject: (id: string) => r(`/api/v1/projects/${encodeURIComponent(id)}/restore`, "POST"),
  moveFiles: (project: string, from: string, to: string) => {
    if (!isSafeRelativePath(from) || !isSafeRelativePath(to)) return Promise.reject(new ApiError(400, "Invalid file path"));
    return r<{ moved: { from: string; to: string }[]; count: number }>(
      `/api/v1/projects/${encodeURIComponent(project)}/files-move`, "POST", { from_path: from, to_path: to });
  },
  deleteFolder: (project: string, folder: string) => {
    if (!isSafeRelativePath(folder)) return Promise.reject(new ApiError(400, "Invalid folder path"));
    return r<{ folder: string; deleted: number }>(`/api/v1/projects/${encodeURIComponent(project)}/folders/${encodePath(folder)}`, "DELETE");
  },
  deleteFile: (project: string, path: string) => {
    if (!isSafeRelativePath(path)) return Promise.reject(new ApiError(400, "Invalid file path"));
    return r<{ version: number }>(`/api/v1/projects/${encodeURIComponent(project)}/files/${encodePath(path)}`, "DELETE");
  },
  history: (project: string, path: string) =>
    r<FileVersion[]>(`/api/v1/projects/${encodeURIComponent(project)}/history?path=${encodeURIComponent(path)}`),
  restoreFile: (project: string, path: string, version: number) =>
    r<{ path: string; content: string; version: number }>(
      `/api/v1/projects/${encodeURIComponent(project)}/restore-file`, "POST", { path, version }),
  members: () => r<Member[]>("/api/v1/members"),
  setMember: (subject: string, role: string) =>
    r<Member>(`/api/v1/members/${encodeURIComponent(subject)}`, "PUT", { role }),
  permissions: () => r<{ role: string; permissions: Record<string, string> }>("/api/v1/me/permissions"),
  auditEvents: (limit = 100) => r<AuditEvent[]>(`/api/v1/audit-events?limit=${limit}`),
  verifyAudit: () => r<{ intact: boolean; first_broken_event: number | null }>("/api/v1/audit-events/verify"),
  files: (project: string) => r<FileEntry[]>(`/api/v1/projects/${encodeURIComponent(project)}/files`),
  saveFile: (project: string, path: string, content: string) => {
    if (!isSafeRelativePath(path)) return Promise.reject(new ApiError(400, "Invalid file path"));
    return r(`/api/v1/projects/${encodeURIComponent(project)}/files/${encodePath(path)}`, "PUT", { content });
  },
  runs: (project: string) => r<RunSummary[]>(`/api/v1/projects/${encodeURIComponent(project)}/agent-runs`),
  createRun: (project: string, task: string, provider?: Provider) =>
    r<RunDetail>("/api/v1/agent-runs", "POST",
      { project_id: project, task, ...(provider ? { preferred_provider: provider } : {}) }),
  run: (id: string) => r<RunDetail>(`/api/v1/agent-runs/${encodeURIComponent(id)}`),
  decide: (id: string, approved: boolean) =>
    r(`/api/v1/agent-runs/${encodeURIComponent(id)}/decision?approved=${approved}`, "POST"),
  enqueue: (id: string) =>
    r<{ job_id: string; state: string }>(`/api/v1/agent-runs/${encodeURIComponent(id)}/enqueue`, "POST"),
  cancel: (id: string) => r(`/api/v1/agent-runs/${encodeURIComponent(id)}/cancel`, "POST"),
  retry: (id: string) => r(`/api/v1/agent-runs/${encodeURIComponent(id)}/retry`, "POST"),
  audit: (id: string) => r<AuditEntry[]>(`/api/v1/agent-runs/${encodeURIComponent(id)}/audit`),
  toolApprovals: (id: string) => r<ToolApproval[]>(`/api/v1/agent-runs/${encodeURIComponent(id)}/tool-approvals`),
  requestTool: (id: string, server: string, tool: string, args: Record<string, unknown>) =>
    r<{ id: string; state: string; args_sha256: string }>(
      `/api/v1/agent-runs/${encodeURIComponent(id)}/tool-requests`, "POST", { server, tool, arguments: args }),
  decideTool: (approvalId: string, approved: boolean) =>
    r(`/api/v1/tool-approvals/${encodeURIComponent(approvalId)}/decision?approved=${approved}`, "POST"),
  addKnowledge: (project: string, title: string, content: string) =>
    r<{ id: string; title: string }>(`/api/v1/projects/${encodeURIComponent(project)}/knowledge`, "POST", { title, content }),
  indexKnowledge: (project: string, doc: string) =>
    r<{ chunks_indexed: number }>(
      `/api/v1/projects/${encodeURIComponent(project)}/knowledge/${encodeURIComponent(doc)}/index`, "POST"),
  searchKnowledge: (project: string, query: string) =>
    r<{ matches: LexicalMatch[] }>(`/api/v1/projects/${encodeURIComponent(project)}/knowledge/search`, "POST", { query }),
  vectorSearch: (project: string, query: string) =>
    r<{ matches: VectorMatch[] }>(`/api/v1/projects/${encodeURIComponent(project)}/knowledge/vector-search`, "POST", { query }),
});
export type IdeApi = ReturnType<typeof ideApi>;

/** Which lifecycle actions the UI offers for a run, mirroring supervisor.py transitions. */
export function runActions(status: RunStatus, attempts: number) {
  return {
    decide: status === "awaiting_approval",
    approveAndRun: status === "awaiting_approval",
    enqueue: status === "approved",
    cancel: ["awaiting_approval", "approved", "running", "failed"].includes(status),
    retry: status === "failed" && attempts < 2,
    requestTool: status === "approved" || status === "running",
  };
}

/** Opens (creating on first use) the signed-in user's personal workspace and returns its tenant id. */
export async function ensureWorkspace(base: string, token: string, fetchImpl: typeof fetch = fetch): Promise<string> {
  const response = await fetchImpl(base + "/api/v1/workspace", {
    method: "POST", headers: { Authorization: "Bearer " + token }, cache: "no-store",
  });
  if (!response.ok) throw new ApiError(response.status, `API error ${response.status}`);
  const data = await response.json();
  if (typeof data?.tenant_id !== "string" || !/^u-[0-9a-f]{32}$/.test(data.tenant_id)) throw new ApiError(502, "Invalid workspace");
  return data.tenant_id;
}
