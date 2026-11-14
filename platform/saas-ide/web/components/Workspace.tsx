"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import type { Capabilities, FileEntry, IdeApi, Project } from "../lib/api";
import { ideApi, isSafeRelativePath, makeRequester } from "../lib/api";
import type { Consent } from "../lib/ads";
import { readConsent, writeConsent } from "../lib/ads";
import { buildTree, closeTab, isDirty, languageFor, markSaved, openTab, updateTab, type Tab } from "../lib/workspace";
import AgentPanel from "./AgentPanel";
import KnowledgePanel from "./KnowledgePanel";
import McpOperations from "./McpOperations";
import InstallApp from "./InstallApp";
import FileTree from "./FileTree";
import { AdSlot, ConsentBanner } from "./Ads";

// Monaco is self-hosted from /monaco/vs (copied by scripts/copy-monaco.mjs); never from a CDN.
const Editor = dynamic(async () => {
  const mod = await import("@monaco-editor/react");
  mod.loader.config({ paths: { vs: "/monaco/vs" } });
  return mod.default;
}, { ssr: false, loading: () => <div className="empty muted">Loading editor…</div> });
const apiBase = process.env.NEXT_PUBLIC_IDE_API_URL || "http://localhost:8090";
const issuer = process.env.NEXT_PUBLIC_OIDC_AUTHORITY || "";
const clientId = process.env.NEXT_PUBLIC_OIDC_CLIENT_ID || "";
const tenant = process.env.NEXT_PUBLIC_IDE_TENANT || "";
const manager = () => new UserManager({
  authority: issuer, client_id: clientId, redirect_uri: window.location.origin + "/callback",
  response_type: "code", scope: "openid profile", userStore: new WebStorageStateStore({ store: window.sessionStorage }),
});
type Panel = "agent" | "knowledge" | "ops";

export default function Workspace() {
  const [token, setToken] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [active, setActive] = useState("");
  const [panel, setPanel] = useState<Panel>("agent");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [message, setMessage] = useState("Sign in to load your workspace.");
  const [consent, setConsent] = useState<Consent>("unknown");
  const configured = Boolean(issuer && clientId && tenant);

  const requester = useMemo(() => makeRequester(apiBase, token, tenant), [token]);
  const api: IdeApi | null = useMemo(() => (token ? ideApi(requester) : null), [token, requester]);
  const status = useCallback((m: string) => setMessage(m), []);

  useEffect(() => { setConsent(readConsent(typeof window === "undefined" ? undefined : window.localStorage)); }, []);
  useEffect(() => {
    if (!configured) { setMessage("Set NEXT_PUBLIC_OIDC_AUTHORITY, NEXT_PUBLIC_OIDC_CLIENT_ID and NEXT_PUBLIC_IDE_TENANT to sign in."); return; }
    manager().getUser().then(u => { if (u && !u.expired) setToken(u.access_token); })
      .catch(() => setMessage("Authentication session unavailable"));
  }, [configured]);
  useEffect(() => {
    if (!api) return;
    api.projects().then(p => { setProjects(p); setMessage(p.length ? "Select a project" : "Create your first project"); })
      .catch(e => setMessage(String(e.message ?? e)));
    api.capabilities().then(setCapabilities).catch(() => setCapabilities(null));
  }, [api]);

  const current = tabs.find(t => t.path === active);
  const dirty = useMemo(() => new Set(tabs.filter(isDirty).map(t => t.path)), [tabs]);
  const tree = useMemo(() => buildTree([...files.map(f => f.path), ...tabs.map(t => t.path)]), [files, tabs]);

  async function openProject(id: string) {
    if (!api) return;
    if (dirty.size && !window.confirm("Discard unsaved changes in open tabs?")) return;
    try {
      const data = await api.files(id);
      setProject(id); setFiles(data); setTabs([]); setActive("");
      if (data[0]) { setTabs([{ path: data[0].path, content: data[0].content, saved: data[0].content }]); setActive(data[0].path); }
      setMessage(`Opened ${projects.find(p => p.id === id)?.name ?? "project"} · ${data.length} files`);
    } catch (e) { setMessage(String((e as Error).message ?? e)); }
  }

  function openFile(path: string) {
    const content = tabs.find(t => t.path === path)?.content ?? files.find(f => f.path === path)?.content ?? "";
    setTabs(t => openTab(t, path, content)); setActive(path);
  }

  async function createProject() {
    if (!api) return;
    const name = window.prompt("Project name")?.trim();
    if (!name) return;
    try { const p = await api.createProject(name.slice(0, 120)); setProjects(x => [...x, p]); await openProject(p.id); }
    catch (e) { setMessage(String((e as Error).message ?? e)); }
  }

  function newFile() {
    const name = window.prompt("Relative file path (e.g. src/main.py)")?.trim();
    if (!name) return;
    if (!isSafeRelativePath(name)) { setMessage("Invalid path: use a relative path without '..' or empty segments"); return; }
    setTabs(t => openTab(t, name, "")); setActive(name); setMessage(`New file ${name} (unsaved)`);
  }

  const save = useCallback(async () => {
    if (!api || !project || !current) return;
    try {
      await api.saveFile(project, current.path, current.content);
      setTabs(t => markSaved(t, current.path));
      setFiles(f => [...f.filter(x => x.path !== current.path), { path: current.path, content: current.content }]);
      setMessage("Saved " + current.path);
    } catch (e) { setMessage(String((e as Error).message ?? e)); }
  }, [api, project, current]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); void save(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty.size) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function close(path: string) {
    const tab = tabs.find(t => t.path === path);
    if (tab && isDirty(tab) && !window.confirm(`Close ${path} without saving?`)) return;
    const next = closeTab(tabs, path, active); setTabs(next.tabs); setActive(next.active);
  }

  function chooseConsent(c: "granted" | "denied") { writeConsent(window.localStorage, c); setConsent(c); }

  return <main className="shell">
    <header className="topbar">
      <strong>AEP-X <span>Agentic IDE</span></strong>
      <select aria-label="Project" value={project} disabled={!api} onChange={e => void openProject(e.target.value)}>
        <option value="">{api ? "Select project…" : "Sign in to choose a project"}</option>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <nav>
        <InstallApp />
        {token ? <>
          <button onClick={() => void createProject()}>New project</button>
          <button onClick={() => void manager().signoutRedirect()}>Sign out</button>
        </> : <button className="primary" disabled={!configured} onClick={() => void manager().signinRedirect()}>Sign in with OIDC</button>}
      </nav>
    </header>

    <div className="ide">
      <aside className="explorer" aria-label="Explorer">
        <div className="section-head"><h3>Explorer</h3>{project && <button className="icon" title="New file" aria-label="New file" onClick={newFile}>+</button>}</div>
        {project ? <FileTree nodes={tree} active={active} dirty={dirty} onOpen={openFile} />
          : <p className="muted small">No project open.</p>}
        <AdSlot surface="sidebar" consent={consent} />
      </aside>

      <section className="editor-area" aria-label="Editor">
        <div className="tabs" role="tablist">
          {tabs.map(t => <div key={t.path} role="tab" aria-selected={t.path === active}
            className={"tab" + (t.path === active ? " active" : "")}>
            <button className="tab-name" onClick={() => setActive(t.path)} title={t.path}>
              {t.path.split("/").pop()}{isDirty(t) && <span className="dot"> ●</span>}
            </button>
            <button className="icon" aria-label={"Close " + t.path} onClick={() => close(t.path)}>×</button>
          </div>)}
          <span className="spacer" />
          <button className="primary" disabled={!current || !isDirty(current)} onClick={() => void save()}>Save</button>
        </div>
        {current ? <div className="editor-host"><Editor height="100%" theme="vs-dark" path={current.path}
          language={languageFor(current.path)} value={current.content}
          onChange={v => setTabs(t => updateTab(t, current.path, v ?? ""))}
          options={{ minimap: { enabled: false }, automaticLayout: true, fontSize: 14, scrollBeyondLastLine: false }} /></div>
          : <div className="empty">
              <h2>{project ? "Open a file from the explorer" : "Welcome to AEP-X"}</h2>
              <p className="muted">Plan work with the agent crew, approve each step, and keep a full audit trail.</p>
              <AdSlot surface="projectHome" consent={consent} />
            </div>}
        <footer className="statusbar" role="status">
          <span>{message}</span>
          <span className="spacer" />
          {current && <span>{languageFor(current.path)} · {isDirty(current) ? "unsaved" : "saved"} · Ctrl/⌘+S</span>}
        </footer>
      </section>

      <aside className="side-panel" aria-label="Agent tools">
        <div className="panel-tabs" role="tablist">
          {(["agent", "knowledge", "ops"] as Panel[]).map(p => <button key={p} role="tab" aria-selected={panel === p}
            className={panel === p ? "active" : ""} onClick={() => setPanel(p)}>
            {p === "agent" ? "Agents" : p === "knowledge" ? "Knowledge" : "Operations"}</button>)}
        </div>
        <div className="panel-body">
          {panel === "agent" && <AgentPanel api={api} project={project} capabilities={capabilities} onStatus={status} />}
          {panel === "knowledge" && <KnowledgePanel api={api} project={project} onStatus={status} />}
          {panel === "ops" && <McpOperations request={requester} enabled={Boolean(token)} />}
        </div>
      </aside>
    </div>
    <ConsentBanner consent={consent} onChoose={chooseConsent} />
  </main>;
}
