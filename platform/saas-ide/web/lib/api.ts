// Typed client for the AEP-X IDE backend (platform/saas-ide/backend/app/main.py).
// Every call is tenant-scoped by the X-Tenant-ID header and authorised by the OIDC bearer token;
// the backend re-verifies membership and role, so nothing here is a security boundary.

export type Project = { id: string; name: string; description: string };
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
};
export type LexicalMatch = { id: string; title: string; excerpt: string; score: number };
export type VectorMatch = { document_id: string; excerpt: string; score: number };
export type Provider = "oci" | "openai" | "anthropic" | "gemini";

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
  capabilities: () => r<Capabilities>("/api/v1/agent-capabilities"),
  projects: () => r<Project[]>("/api/v1/projects"),
  createProject: (name: string, description = "") =>
    r<Project>("/api/v1/projects", "POST", { name, description }),
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
    enqueue: status === "approved",
    cancel: ["awaiting_approval", "approved", "running", "failed"].includes(status),
    retry: status === "failed" && attempts < 2,
    requestTool: status === "approved" || status === "running",
  };
}
