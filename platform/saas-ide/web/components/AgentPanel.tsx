"use client";
import { useCallback, useEffect, useState } from "react";
import type { AiUsage, AuditEntry, Capabilities, IdeApi, Provider, RunDetail, RunSummary, ToolApproval } from "../lib/api";
import { runActions } from "../lib/api";
import { QUICK_TASKS, splitResult, usageWidth } from "../lib/agentResult";
import { parsePlan } from "../lib/workspace";

type Props = {
  api: IdeApi | null; project: string; capabilities: Capabilities | null; onStatus: (m: string) => void;
  /** Saves an agent-proposed file into the project and opens it in the editor. */
  onSaveFile?: (path: string, content: string) => Promise<void>;
  /** Quick tasks for the open project's IDE module; defaults to the general set. */
  quickTasks?: { label: string; task: string }[];
};
const ACTIVE = new Set(["awaiting_approval", "approved", "running"]);
const WORKING = new Set(["approved", "running"]);
const PROVIDERS: Provider[] = ["openrouter", "oci", "openai", "anthropic", "gemini"];
const PROVIDER_LABEL: Record<string, string> = { openrouter: "AEP-X AI (OpenRouter)" };

export default function AgentPanel({ api, project, capabilities, onStatus, onSaveFile, quickTasks = QUICK_TASKS }: Props) {
  const [task, setTask] = useState("");
  const [provider, setProvider] = useState<Provider | "">("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [approvals, setApprovals] = useState<ToolApproval[]>([]);
  const [busy, setBusy] = useState(false);
  const [tool, setTool] = useState({ server: "", name: "", args: "{}" });
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const live = Boolean(capabilities?.agents_live);

  const fail = useCallback((e: unknown) => onStatus(e instanceof Error ? e.message : String(e)), [onStatus]);

  const refreshRuns = useCallback(async () => {
    if (!api || !project) { setRuns([]); return; }
    try { setRuns(await api.runs(project)); } catch (e) { fail(e); }
  }, [api, project, fail]);

  const refreshRun = useCallback(async (id: string) => {
    if (!api || !id) return;
    try {
      const [d, a, t] = await Promise.all([api.run(id), api.audit(id), api.toolApprovals(id)]);
      setDetail(d); setAudit(a); setApprovals(t);
    } catch (e) { fail(e); }
  }, [api, fail]);

  const refreshUsage = useCallback(async () => {
    if (!api || !live) { setUsage(null); return; }
    try { setUsage(await api.aiUsage()); } catch { setUsage(null); }
  }, [api, live]);

  useEffect(() => { void refreshUsage(); }, [refreshUsage]);
  useEffect(() => { if (detail && !ACTIVE.has(detail.status)) void refreshUsage(); }, [detail, refreshUsage]);
  useEffect(() => { setSelected(""); setDetail(null); void refreshRuns(); }, [refreshRuns]);
  useEffect(() => { if (selected) void refreshRun(selected); }, [selected, refreshRun]);
  // Poll only while the selected run can still change.
  useEffect(() => {
    if (!selected || !detail || !ACTIVE.has(detail.status)) return;
    const timer = window.setInterval(() => { void refreshRun(selected); void refreshRuns(); },
      WORKING.has(detail.status) ? 2500 : 5000);
    return () => window.clearInterval(timer);
  }, [selected, detail, refreshRun, refreshRuns]);

  async function act(label: string, fn: () => Promise<unknown>, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    try { await fn(); onStatus(label); await refreshRuns(); if (selected) await refreshRun(selected); }
    catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function submit() {
    if (!api || !project || task.trim().length < 5) return;
    setBusy(true);
    try {
      const run = await api.createRun(project, task.trim(), provider || undefined);
      setTask(""); onStatus(live ? "Plan ready: review it, then Approve & run." : "Plan created — human approval required before execution.");
      await refreshRuns(); setSelected(run.id);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }

  async function approveAndRun(id: string) {
    if (!api) return;
    await act("Approved — the agents are working on it", async () => {
      await api.decide(id, true);
      await api.enqueue(id);
    }, "Approve this plan and let the AI agents run it? Approval is audited; nothing is executed or published without you.");
  }

  async function saveBlock(file: string, code: string) {
    if (!onSaveFile) return;
    try { await onSaveFile(file, code.endsWith("\n") ? code : code + "\n"); onStatus("Saved " + file + " to the project"); }
    catch (e) { fail(e); }
  }

  async function copy(code: string) {
    try { await navigator.clipboard.writeText(code); onStatus("Copied"); } catch { onStatus("Copy is not available here"); }
  }

  function requestTool() {
    if (!api || !selected) return;
    let args: Record<string, unknown>;
    try {
      const parsed = JSON.parse(tool.args || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
      args = parsed;
    } catch { onStatus("Tool arguments must be a JSON object"); return; }
    void act("Tool request recorded; awaiting owner/admin approval",
      () => api.requestTool(selected, tool.server, tool.name.trim(), args));
  }

  const enabledProviders = capabilities ? PROVIDERS.filter(p => capabilities.providers[p]) : PROVIDERS;
  const actions = detail ? runActions(detail.status, runs.find(r => r.id === detail.id)?.attempts ?? 0) : null;
  const plan = detail ? parsePlan(detail.plan) : [];

  if (!project) return <p className="muted">Open a project to plan agent work.</p>;

  const blocks = detail?.result ? splitResult(detail.result) : [];

  return <div className="agent">
    <div className={"assistant-status" + (live ? " live" : "")} role="status">
      <span className="dot" aria-hidden="true" />
      {live ? <span><strong>AI agents live.</strong> Describe a task, review the plan, approve — the crew does the rest.</span>
        : <span><strong>Planning mode.</strong> Agents draft plans for approval; live AI execution is not switched on here.</span>}
      {live && usage && <div className="usage" title={`${usage.plan} plan · resets at midnight UTC`}>
        <span className="muted small">Today ({usage.plan}): {usage.used_today_percent}% used</span>
        <span className="usage-bar"><span style={{ width: usageWidth(usage.used_today_percent) }} /></span>
        {!usage.platform_budget_available && <span className="muted small">Monthly AI budget reached — agents resume next month.</span>}
      </div>}
    </div>
    <div className="chips" aria-label="Quick tasks">
      {quickTasks.map(q => <button key={q.task} className="chip" onClick={() => setTask(q.task)}>{q.label}</button>)}
    </div>
    <div className="compose">
      <textarea aria-label="Agent task" rows={3} maxLength={4000} value={task}
        placeholder="Describe a software engineering task for the agent crew…"
        onChange={e => setTask(e.target.value)}
        onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void submit(); }} />
      <div className="row">
        <label>Model <select value={provider} onChange={e => setProvider(e.target.value as Provider | "")}>
          <option value="">Auto route</option>
          {PROVIDERS.map(p => <option key={p} value={p} disabled={!enabledProviders.includes(p)}>
            {PROVIDER_LABEL[p] ?? p}{enabledProviders.includes(p) ? "" : " (disabled)"}</option>)}
        </select></label>
        <button className="primary" disabled={busy || task.trim().length < 5} onClick={() => void submit()}>{live ? "Ask the agents" : "Plan task"}</button>
      </div>
      {capabilities && <p className="muted small">
        {`Approval ${capabilities.approval_required ? "required" : "optional"} · knowledge: ${capabilities.knowledge_retrieval} · MCP execution ${capabilities.mcp_execution_enabled ? "on" : "off"}`}
      </p>}
    </div>

    <div className="runs" role="list" aria-label="Agent runs">
      {runs.length === 0 && <p className="muted">No runs yet.</p>}
      {runs.map(r => <button role="listitem" key={r.id} className={"run" + (selected === r.id ? " active" : "")}
        onClick={() => setSelected(r.id)}>
        <span className={"badge " + r.status}>{r.status.replace(/_/g, " ")}</span>
        <span className="run-task">{r.task}</span>
      </button>)}
    </div>

    {detail && actions && <article className="run-detail" aria-label="Selected run">
      <header>
        <span className={"badge " + detail.status}>{detail.status.replace(/_/g, " ")}</span>
        <span className="muted small">route: {detail.model_route}</span>
      </header>
      <h4>Plan</h4>
      <ol className="plan">{plan.map((s, i) => <li key={i}><strong>{s.title}</strong>{s.detail && <span> — {s.detail}</span>}</li>)}</ol>
      {WORKING.has(detail.status) && live && <p className="working" role="status">
        <span className="spinner" aria-hidden="true" /> The agents are working on it…</p>}
      {blocks.length > 0 && <><h4>Result</h4><div className="answer">
        {blocks.map((b, i) => b.kind === "text"
          ? <p key={i} className="answer-text">{b.text}</p>
          : <figure key={i} className="answer-code">
              <figcaption>
                <code>{b.file ?? (b.lang || "code")}</code>
                <span className="spacer" />
                <button onClick={() => void copy(b.code)}>Copy</button>
                {b.file && onSaveFile && <button className="primary" onClick={() => void saveBlock(b.file!, b.code)}>Save to project</button>}
              </figcaption>
              <pre>{b.code}</pre>
            </figure>)}
      </div></>}
      <div className="row wrap">
        {actions.approveAndRun && live && <button className="primary" disabled={busy}
          onClick={() => void approveAndRun(detail.id)}>Approve &amp; run</button>}
        {actions.decide && !live && <>
          <button className="primary" disabled={busy} onClick={() => void act("Plan approved",
            () => api!.decide(detail.id, true), "Approve this plan? Approval is audited.")}>Approve plan</button>
        </>}
        {actions.decide && <button disabled={busy} onClick={() => void act("Plan rejected", () => api!.decide(detail.id, false))}>Reject</button>}
        {actions.enqueue && <button className="primary" disabled={busy}
          onClick={() => void act("Queued for the governed worker", () => api!.enqueue(detail.id))}>Queue for execution</button>}
        {actions.cancel && <button disabled={busy}
          onClick={() => void act("Run cancelled", () => api!.cancel(detail.id), "Cancel this run?")}>Cancel</button>}
        {actions.retry && <button disabled={busy}
          onClick={() => void act("Retry requested; re-approval required", () => api!.retry(detail.id))}>Retry</button>}
      </div>

      <h4>Tool approvals</h4>
      {approvals.length === 0 && <p className="muted small">No tool requests.</p>}
      <ul className="approvals">{approvals.map(a => <li key={a.id}>
        <code>{a.server}.{a.tool}</code> <span className={"badge " + a.state}>{a.state}</span>
        <span className="muted small" title={a.args_sha256}> args {a.args_sha256.slice(0, 12)}…</span>
        {a.state === "pending" && <span className="row">
          <button disabled={busy} onClick={() => void act("Tool approved", () => api!.decideTool(a.id, true),
            `Approve ${a.server}.${a.tool} with arguments digest ${a.args_sha256.slice(0, 16)}…? Single use; audited.`)}>Approve</button>
          <button disabled={busy} onClick={() => void act("Tool rejected", () => api!.decideTool(a.id, false))}>Reject</button>
        </span>}
      </li>)}</ul>
      {actions.requestTool && capabilities && capabilities.mcp_allowlisted_servers.length > 0 && <details>
        <summary>Request an MCP tool call</summary>
        <div className="row wrap">
          <select aria-label="MCP server" value={tool.server} onChange={e => setTool(t => ({ ...t, server: e.target.value }))}>
            <option value="">Server…</option>
            {capabilities.mcp_allowlisted_servers.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <input aria-label="Tool name" placeholder="tool" maxLength={120} value={tool.name}
            onChange={e => setTool(t => ({ ...t, name: e.target.value }))} />
        </div>
        <textarea aria-label="Tool arguments JSON" rows={2} maxLength={4000} value={tool.args}
          onChange={e => setTool(t => ({ ...t, args: e.target.value }))} />
        <button disabled={busy || !tool.server || !tool.name.trim()} onClick={requestTool}>Request approval</button>
      </details>}

      <h4>Audit trail</h4>
      <ol className="audit">{audit.map((a, i) => <li key={i}><code>{a.action}</code> <span className="muted small">by {a.actor}</span></li>)}</ol>
    </article>}
  </div>;
}
