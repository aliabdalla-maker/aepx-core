"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { oidcAuthority, oidcClientId, oidcConfigured, oidcManager, oidcRegistrationManager } from "../lib/auth";
import { DEFAULT_AUTH_OPTIONS, fetchAuthOptions, forgotPasswordUrl, releaseLabel, saveHint, signinArgs, type AuthOptions } from "../lib/signin";
import SignedOutWelcome from "./SignedOutWelcome";
import Assistant from "./Assistant";
import ImportDialog from "./ImportDialog";
import type { Capabilities, Entitlement, FileEntry, IdeApi, IdeModule, Project } from "../lib/api";
import { ensureWorkspace, ideApi, isSafeRelativePath, makeBlobFetcher, makeRequester } from "../lib/api";
import type { Consent } from "../lib/ads";
import { readConsent, writeConsent } from "../lib/ads";
import { buildTree, closeTab, isDirty, languageFor, markSaved, openTab, updateTab, type Tab } from "../lib/workspace";
import AgentPanel from "./AgentPanel";
import KnowledgePanel from "./KnowledgePanel";
import McpOperations from "./McpOperations";
import StudioPanel from "./StudioPanel";
import InstallApp from "./InstallApp";
import FileTree from "./FileTree";
import { AdSlot, ConsentBanner } from "./Ads";
import PlanBanner from "./PlanBanner";
import ModuleLauncher from "./ModuleLauncher";
import FileHistory from "./FileHistory";
import TeamPanel from "./TeamPanel";
import ModuleEditor, { hasVisualEditor } from "./ModuleEditors";
import { moduleLabel, moduleTasks } from "../lib/modules";
import { QUICK_TASKS } from "../lib/agentResult";

// Monaco is self-hosted from /monaco/vs (copied by scripts/copy-monaco.mjs); never from a CDN.
const Editor = dynamic(async () => {
  const mod = await import("@monaco-editor/react");
  mod.loader.config({ paths: { vs: "/monaco/vs" } });
  return mod.default;
}, { ssr: false, loading: () => <div className="empty muted">Loading editor…</div> });
const apiBase = process.env.NEXT_PUBLIC_IDE_API_URL || "http://localhost:8090";
// A fixed tenant is optional. Without one, each user gets a personal workspace on first sign-in.
const fixedTenant = process.env.NEXT_PUBLIC_IDE_TENANT || "";
const manager = oidcManager;
type Panel = "agent" | "studio" | "knowledge" | "team" | "ops";

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
  const [entitlement, setEntitlement] = useState<Entitlement | null>(null);
  const [tenant, setTenant] = useState(fixedTenant);
  const [modules, setModules] = useState<IdeModule[]>([]);
  const [launcher, setLauncher] = useState(false);
  const [launchModule, setLaunchModule] = useState<string | undefined>(undefined);
  const [historyFor, setHistoryFor] = useState("");
  // Files with a visual editor (music, audio, storyboard, animation, OpenAPI, catalogue) open in it;
  // the Code view shows the same file as text.
  const [codeView, setCodeView] = useState<Set<string>>(new Set());
  const configured = oidcConfigured;
  const [authOptions, setAuthOptions] = useState<AuthOptions>(DEFAULT_AUTH_OPTIONS);
  const [apiRelease, setApiRelease] = useState<string | null>(null);
  const release = releaseLabel(process.env.NEXT_PUBLIC_RELEASE_SHA, apiRelease);
  const signIn = (kind: "email" | "create" | "google" | "github") =>
    void (kind === "create" ? oidcRegistrationManager() : manager()).signinRedirect(signinArgs(kind));
  // Public, unauthenticated: which sign-in methods work here, and which API build is live.
  useEffect(() => {
    void fetchAuthOptions(apiBase).then(setAuthOptions);
    fetch(apiBase + "/api/v1/version", { credentials: "omit" }).then(r => (r.ok ? r.json() : null))
      .then(v => setApiRelease(v?.release_sha ?? null)).catch(() => setApiRelease(null));
  }, []);

  const requester = useMemo(() => makeRequester(apiBase, token, tenant), [token, tenant]);
  const fetchAsset = useMemo(() => makeBlobFetcher(apiBase, token, tenant), [token, tenant]);
  const [role, setRole] = useState<string | undefined>(undefined);
  const api: IdeApi | null = useMemo(() => (token && tenant ? ideApi(requester) : null), [token, tenant, requester]);
  const status = useCallback((m: string) => setMessage(m), []);

  useEffect(() => {
    if (!token || fixedTenant) return;
    let cancelled = false;
    ensureWorkspace(apiBase, token)
      .then(id => { if (!cancelled) setTenant(id); })
      .catch(() => { if (!cancelled) setMessage("Could not open your workspace. Try signing in again."); });
    return () => { cancelled = true; };
  }, [token]);

  // Deep link from the VS Code / JetBrains plugins: /?new=<module> opens the new-project dialog.
  // Kept in sessionStorage so it survives the sign-in redirect.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("new");
    if (wanted && /^[a-z0-9-]{1,32}$/.test(wanted)) {
      try { window.sessionStorage.setItem("aepx.new", wanted); } catch { /* storage unavailable */ }
      const url = new URL(window.location.href); url.searchParams.delete("new");
      window.history.replaceState(null, "", url.pathname + url.search);
    }
  }, []);
  useEffect(() => {
    if (!api) return;
    let wanted: string | null = null;
    try { wanted = window.sessionStorage.getItem("aepx.new"); window.sessionStorage.removeItem("aepx.new"); } catch { /* ignore */ }
    if (wanted) { setLaunchModule(wanted); setLauncher(true); }
  }, [api]);
  useEffect(() => { setConsent(readConsent(typeof window === "undefined" ? undefined : window.localStorage)); }, []);
  useEffect(() => {
    if (!configured) { setMessage("Set NEXT_PUBLIC_OIDC_AUTHORITY and NEXT_PUBLIC_OIDC_CLIENT_ID to sign in."); return; }
    const m = manager();
    m.getUser().then(u => { if (u && !u.expired) setToken(u.access_token); })
      .catch(() => setMessage("Authentication session unavailable"));
    // Silent renewal keeps the session alive; on failure keep open tabs and ask to sign in again.
    const onLoaded = (u: { access_token: string }) => setToken(u.access_token);
    const onExpired = () => { setToken(""); setMessage("Session expired — sign in again. Unsaved tabs are kept in this window."); };
    const onRenewError = () => setMessage("Session renewal failed — save your work and sign in again.");
    m.events.addUserLoaded(onLoaded);
    m.events.addAccessTokenExpired(onExpired);
    m.events.addSilentRenewError(onRenewError);
    return () => {
      m.events.removeUserLoaded(onLoaded);
      m.events.removeAccessTokenExpired(onExpired);
      m.events.removeSilentRenewError(onRenewError);
    };
  }, [configured]);
  useEffect(() => {
    if (!api) return;
    api.projects().then(p => { setProjects(p); setMessage(p.length ? "Select a project" : "Create your first project"); })
      .catch(e => setMessage(String(e.message ?? e)));
    api.capabilities().then(setCapabilities).catch(() => setCapabilities(null));
    api.modules().then(setModules).catch(() => setModules([]));
    api.me().then(m => setRole(m.role)).catch(() => setRole(undefined));
    // Server-side plan: trial (100% ads) -> Pro £4.99/month (5% ads) -> free (100% ads).
    api.entitlement().then(setEntitlement).catch(() => setEntitlement(null));
    const billing = new URLSearchParams(window.location.search).get("billing");
    if (billing === "success") setMessage("Thanks for subscribing — your plan updates as soon as Stripe confirms payment.");
    if (billing) window.history.replaceState(null, "", window.location.pathname);
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

  function createProject() { if (api) { setLaunchModule(undefined); setLauncher(true); } }

  async function projectCreated(p: Project) {
    setLauncher(false); setProjects(x => [...x, p]);
    if (!api) return;
    // Open directly (the projects list in state may not include it yet).
    try {
      const data = await api.files(p.id);
      setProject(p.id); setFiles(data); setTabs([]); setActive(""); setHistoryFor("");
      if (data[0]) { setTabs([{ path: data[0].path, content: data[0].content, saved: data[0].content }]); setActive(data[0].path); }
      setMessage(`Created ${p.name} · ${moduleLabel(modules, p.module)}`);
    } catch (e) { setMessage(String((e as Error).message ?? e)); }
  }

  async function deleteFile(path: string) {
    if (!api || !project) return;
    if (!window.confirm(`Delete ${path}? You can restore it from its history.`)) return;
    try {
      const r = await api.deleteFile(project, path);
      setFiles(f => f.filter(x => x.path !== path));
      setTabs(t => t.filter(x => x.path !== path)); if (active === path) setActive("");
      setMessage(`Deleted ${path} (version ${r.version} kept in history)`);
    } catch (e) { setMessage(String((e as Error).message ?? e)); }
  }

  function restored(path: string, content: string) {
    setFiles(f => [...f.filter(x => x.path !== path), { path, content }]);
    setTabs(t => markSaved(openTab(t.filter(x => x.path !== path), path, content), path)); setActive(path);
  }

  const currentProject = projects.find(p => p.id === project);
  const agentTasks = useMemo(() => moduleTasks(modules, currentProject?.module, QUICK_TASKS), [modules, currentProject]);
  const [importOpen, setImportOpen] = useState(false);
  const readOnly = role === "viewer" || role === "reviewer";
  const assistantModule = currentProject ? (currentProject.module || "software") : "general";
  const assistantModuleName = currentProject ? moduleLabel(modules, currentProject.module) : "AEP-X IDE";

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

  // Agent answers can propose whole files: save them into the project and open them.
  const saveAgentFile = useCallback(async (path: string, content: string) => {
    if (!api || !project) throw new Error("Open a project first");
    if (!isSafeRelativePath(path)) throw new Error("Invalid file path");
    await api.saveFile(project, path, content);
    setFiles(f => [...f.filter(x => x.path !== path), { path, content }]);
    setTabs(t => markSaved(openTab(t.filter(x => x.path !== path), path, content), path));
    setActive(path);
  }, [api, project]);

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
        {projects.map(p => <option key={p.id} value={p.id}>{p.name} · {moduleLabel(modules, p.module)}</option>)}
      </select>
      <nav>
        <PlanBanner api={api} entitlement={entitlement} onStatus={status} onEntitlement={setEntitlement} />
        <InstallApp />
        {token ? <>
          <button onClick={() => void createProject()}>New project</button>
          <button onClick={() => void manager().signoutRedirect()}>Sign out</button>
        </> : configured && <button className="primary" onClick={() => signIn("email")}>Sign in</button>}
      </nav>
    </header>

    <div className="ide">
      <aside className="explorer" aria-label="Explorer">
        <div className="section-head"><h3>Explorer</h3>{project && <span>
          {api && !readOnly && <button className="icon" title="Import files, a folder or a .zip" aria-label="Import files"
            onClick={() => setImportOpen(true)}>⇪</button>}
          <button className="icon" title="New file" aria-label="New file" onClick={newFile}>+</button></span>}</div>
        {project ? <FileTree nodes={tree} active={active} dirty={dirty} onOpen={openFile} />
          : <p className="muted small">No project open.</p>}
        <AdSlot surface="sidebar" consent={consent} rate={entitlement?.ad_rate ?? 1} />
      </aside>

      <section className="editor-area" aria-label="Editor">
        <div className="tabs">
          {/* Open files are a navigation list (each tab has its own close button), not an ARIA
              tablist, which may not contain nested interactive controls. */}
          <nav aria-label="Open files" className="tab-strip">
            {tabs.map(t => <div key={t.path} className={"tab" + (t.path === active ? " active" : "")}>
              <button className="tab-name" onClick={() => setActive(t.path)} title={t.path}
                aria-current={t.path === active ? "page" : undefined}>
                {t.path.split("/").pop()}{isDirty(t) && <span className="dot" aria-label="unsaved"> ●</span>}
              </button>
              <button className="icon" aria-label={"Close " + t.path} onClick={() => close(t.path)}>×</button>
            </div>)}
          </nav>
          <span className="spacer" />
          {current && hasVisualEditor(current.path) && <div className="seg" role="group" aria-label="View">
            <button aria-pressed={!codeView.has(current.path)} onClick={() => setCodeView(v => { const n = new Set(v); n.delete(current.path); return n; })}>Visual</button>
            <button aria-pressed={codeView.has(current.path)} onClick={() => setCodeView(v => new Set(v).add(current.path))}>Code</button>
          </div>}
          {current && <button onClick={() => setHistoryFor(h => h === current.path ? "" : current.path)}
            aria-pressed={historyFor === current.path}>History</button>}
          {current && <button onClick={() => void deleteFile(current.path)}>Delete</button>}
          {(() => { const hint = saveHint({ signedIn: Boolean(token), hasFile: Boolean(current), dirty: Boolean(current && isDirty(current)) });
            return <button className="primary" disabled={!current || !isDirty(current)} title={hint} aria-description={hint}
              onClick={() => void save()}>Save</button>; })()}
        </div>
        {current && hasVisualEditor(current.path) && !codeView.has(current.path)
          ? <div className="editor-host visual"><ModuleEditor path={current.path} content={current.content}
              onChange={text => setTabs(t => updateTab(t, current.path, text))} onStatus={status} onSaveFile={saveAgentFile} /></div>
          : current ? <div className="editor-host"><Editor height="100%" theme="aepx-dark" path={current.path}
          beforeMount={monaco => monaco.editor.defineTheme("aepx-dark", {
            base: "vs-dark", inherit: true, colors: {},
            // vs-dark comments (#608B4E) are 4.2:1 on #1E1E1E; WCAG AA needs 4.5:1.
            rules: [{ token: "comment", foreground: "6A9955" }],
          })}
          language={languageFor(current.path)} value={current.content}
          onChange={v => setTabs(t => updateTab(t, current.path, v ?? ""))}
          options={{ minimap: { enabled: false }, automaticLayout: true, fontSize: 14, scrollBeyondLastLine: false }} /></div>
          : <div className="empty">
              {!token ? <SignedOutWelcome configured={configured} options={authOptions}
                  forgotUrl={configured ? forgotPasswordUrl(oidcAuthority, oidcClientId) : ""} onSignIn={signIn} />
                : <><h2>{project ? "Open a file from the explorer" : "Welcome to AEP-X"}</h2>
                  <p className="muted">{project ? "Plan work with the agent crew, approve each step, and keep a full audit trail."
                    : projects.length ? "Choose a project at the top, or start a new one." : "Create your first project to get started."}</p>
                  {!project && <button className="primary" onClick={() => void createProject()}>New project</button>}</>}
              <AdSlot surface="projectHome" consent={consent} rate={entitlement?.ad_rate ?? 1} />
            </div>}
        {api && project && historyFor && <FileHistory api={api} project={project} path={historyFor}
          onRestored={restored} onStatus={status} onClose={() => setHistoryFor("")} />}
        <footer className="statusbar" role="status">
          <span>{message}</span>
          <span className="spacer" />
          {current && <span>{languageFor(current.path)} · {isDirty(current) ? "unsaved" : "saved"} · Ctrl/⌘+S</span>}
          {release.text && <span className={release.drift ? "warn" : "muted"}
            title={release.drift ? "The web app and API are on different builds; reload, and if it persists the deploy is incomplete." : "Deployed build"}>
            {release.text}</span>}
        </footer>
      </section>

      <aside className="side-panel" aria-label="Agent tools">
        <div className="panel-tabs" role="tablist">
          {(["agent", "studio", "knowledge", "team", "ops"] as Panel[]).map(p => <button key={p} role="tab" aria-selected={panel === p}
            className={panel === p ? "active" : ""} onClick={() => setPanel(p)}>
            {{ agent: "Agents", studio: "Studio", knowledge: "Knowledge", team: "Team", ops: "Operations" }[p]}</button>)}
        </div>
        <div className="panel-body">
          {panel === "agent" && <AgentPanel api={api} project={project} capabilities={capabilities} onStatus={status} onSaveFile={saveAgentFile} quickTasks={agentTasks} />}
          {panel === "team" && <TeamPanel api={api} role={role} onStatus={status} />}
          {panel === "studio" && <StudioPanel request={requester} fetchAsset={fetchAsset} project={project} role={role} onStatus={status} />}
          {panel === "knowledge" && <KnowledgePanel api={api} project={project} onStatus={status} />}
          {panel === "ops" && <McpOperations request={requester} enabled={Boolean(token)} />}
        </div>
      </aside>
    </div>
    <ConsentBanner consent={consent} onChoose={chooseConsent} />
    {launcher && api && <ModuleLauncher api={api} initial={launchModule} onCreated={p => void projectCreated(p)}
      onClose={() => setLauncher(false)} onStatus={status} />}
    {importOpen && api && project && <ImportDialog api={api} project={project}
      existing={new Set(files.map(f => f.path))} onClose={() => setImportOpen(false)} onStatus={status}
      onImported={saved => setFiles(f => [...f.filter(x => !saved.some(s => s.path === x.path)), ...saved])} />}
    <Assistant api={api} signedIn={Boolean(token)} project={project} module={assistantModule}
      moduleName={assistantModuleName} file={current?.path} agentsLive={Boolean(capabilities?.agents_live)}
      role={role} onStatus={status} onSaveFile={project ? saveAgentFile : undefined} />
  </main>;
}
