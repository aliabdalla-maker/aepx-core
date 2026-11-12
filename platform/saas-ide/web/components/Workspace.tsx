"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import AgentDashboard from "./AgentDashboard";
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });
const api = process.env.NEXT_PUBLIC_IDE_API_URL || "http://localhost:8090";
const issuer = process.env.NEXT_PUBLIC_OIDC_AUTHORITY || "";
const clientId = process.env.NEXT_PUBLIC_OIDC_CLIENT_ID || "";
const tenant = process.env.NEXT_PUBLIC_IDE_TENANT || "";
type Project = { id: string; name: string; description: string };
type FileEntry = { path: string; content: string };
const manager = () => new UserManager({ authority: issuer, client_id: clientId, redirect_uri: window.location.origin + "/callback", response_type: "code", scope: "openid profile", userStore: new WebStorageStateStore({ store: window.sessionStorage }) });
export default function Workspace() {
  const [token, setToken] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [path, setPath] = useState("main.py");
  const [code, setCode] = useState("# Start building with AEP-X\n");
  const [message, setMessage] = useState("Sign in to load your workspace.");
  const configured = Boolean(issuer && clientId && tenant);
  const request = useCallback(async (url: string, method = "GET", body?: unknown) => {
    if (!token) throw new Error("Sign in first");
    const r = await fetch(api + url, { method, headers: { Authorization: "Bearer " + token, "X-Tenant-ID": tenant, ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
    if (!r.ok) throw new Error("API error " + r.status);
    return r.json();
  }, [token]);
  useEffect(() => { if (configured) manager().getUser().then(u => { if (u && !u.expired) setToken(u.access_token); }).catch(() => setMessage("Authentication session unavailable")); }, [configured]);
  useEffect(() => { if (token) request("/api/v1/projects").then(setProjects).catch(e => setMessage(e.message)); }, [token, request]);
  async function openProject(id: string) { try { setProject(id); const data: FileEntry[] = await request("/api/v1/projects/" + id + "/files"); setFiles(data); const first = data[0]; setPath(first?.path || "main.py"); setCode(first?.content || "# Start building with AEP-X\n"); setMessage("Workspace loaded"); } catch(e) { setMessage(String(e)); } }
  async function createProject() { const name = window.prompt("Project name"); if (!name?.trim()) return; try { const p: Project = await request("/api/v1/projects", "POST", { name: name.trim(), description: "" }); setProjects(x => [...x, p]); await openProject(p.id); } catch(e) { setMessage(String(e)); } }
  async function save() { if (!project) return; try { await request("/api/v1/projects/" + project + "/files/" + path.split("/").map(encodeURIComponent).join("/"), "PUT", { content: code }); setFiles(x => [...x.filter(f => f.path !== path), { path, content: code }]); setMessage("Saved " + path); } catch(e) { setMessage(String(e)); } }
  function openFile(f: FileEntry) { setPath(f.path); setCode(f.content); }
  function newFile() { const name = window.prompt("Relative file path (e.g. src/main.py)"); if (!name || name.startsWith("/") || name.split("/").some(p => !p || p === ".." || p === ".") || name.includes("\\")) return; setPath(name); setCode(""); }
  return <main className="shell"><header><strong>AEP-X <span>Hybrid IDE</span></strong><nav>{token ? <><button onClick={createProject}>New project</button><button onClick={() => manager().signoutRedirect()}>Sign out</button></> : <button disabled={!configured} onClick={() => manager().signinRedirect()}>Sign in with OIDC</button>}</nav></header><div className="layout"><aside><h3>Projects</h3>{projects.map(p => <button className={project === p.id ? "active" : ""} key={p.id} onClick={() => openProject(p.id)}>{p.name}</button>)}<hr/><h3>Files</h3>{files.map(f => <button key={f.path} onClick={() => openFile(f)}>{f.path}</button>)}{project && <button onClick={newFile}>+ New file</button>}</aside><section><div className="toolbar"><span>{project ? path : "Select or create a project"}</span><button disabled={!project} onClick={save}>Save</button></div><Editor height="calc(100vh - 180px)" theme="vs-dark" path={path} language={path.endsWith(".py") ? "python" : path.endsWith(".json") ? "json" : "typescript"} value={code} onChange={v => setCode(v || "")} options={{ minimap: { enabled: false }, automaticLayout: true }}/><footer role="status">{message}</footer><AgentDashboard project={project} request={request}/></section></div></main>;
}
