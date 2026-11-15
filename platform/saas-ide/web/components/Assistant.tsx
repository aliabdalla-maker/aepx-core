"use client";
// AEP-X Assistant, available on every screen. Help answers come instantly from the help file and
// cost nothing. "Ask AI" goes through the governed agent pipeline: the request is a normal agent
// run, approved by someone allowed to approve, metered against the daily allowance and monthly cap.
import { useEffect, useRef, useState } from "react";
import type { IdeApi } from "../lib/api";
import { splitResult } from "../lib/agentResult";
import { FINAL_STATUSES, aiAvailability, buildAiTask, loadHelp, searchHelp, suggestedTopics, type HelpTopic } from "../lib/assistant";

type Message =
  | { id: number; from: "you"; text: string }
  | { id: number; from: "help"; question: string; topics: HelpTopic[] }
  | { id: number; from: "ai"; runId: string; status: string; text: string };

type Props = {
  api: IdeApi | null; signedIn: boolean; project: string; module: string; moduleName: string;
  file?: string; agentsLive: boolean; role?: string; onStatus: (m: string) => void;
  onSaveFile?: (path: string, content: string) => Promise<void>;
};

const APPROVERS = new Set(["owner", "admin", "reviewer"]);
const READ_ONLY = new Set(["viewer", "reviewer"]);
const POLL_LIMIT_MS = 10 * 60 * 1000;

export default function Assistant(p: Props) {
  const [open, setOpen] = useState(false);
  const [topics, setTopics] = useState<HelpTopic[]>([]);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);
  const ai = aiAvailability({ signedIn: p.signedIn, project: p.project, agentsLive: p.agentsLive,
    readOnly: p.role ? READ_ONLY.has(p.role) : false });

  useEffect(() => { if (open && !topics.length) void loadHelp().then(setTopics); }, [open, topics.length]);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  type NewMessage = Message extends infer M ? (M extends Message ? Omit<M, "id"> : never) : never;
  const add = (m: NewMessage) => setMessages(list => [...list, { ...m, id: ++seq.current } as Message]);
  const updateAi = (runId: string, patch: Partial<{ status: string; text: string }>) =>
    setMessages(list => list.map(m => (m.from === "ai" && m.runId === runId ? { ...m, ...patch } : m)));

  function askHelp(text = question) {
    const q = text.trim();
    if (q.length < 2) return;
    add({ from: "you", text: q });
    add({ from: "help", question: q, topics: searchHelp(topics, q, p.module) });
    setQuestion("");
  }

  async function poll(runId: string) {
    const started = Date.now();
    while (Date.now() - started < POLL_LIMIT_MS) {
      await new Promise(r => setTimeout(r, 2500));
      try {
        const run = await p.api!.run(runId);
        if (FINAL_STATUSES.has(run.status)) {
          updateAi(runId, { status: run.status, text: run.result || (run.status === "succeeded" ? "(No answer text.)" : "The AI could not answer this time.") });
          return;
        }
        updateAi(runId, { status: run.status });
      } catch { /* transient; keep polling until the limit */ }
    }
    updateAi(runId, { status: "waiting", text: "Still waiting. You can follow this request in the Agents tab." });
  }

  async function askAi(q: string, related: HelpTopic[]) {
    if (!p.api || !ai.ok || busy) return;
    const canApprove = Boolean(p.role && APPROVERS.has(p.role));
    if (canApprove && !window.confirm("Send this question to the AEP-X AI? It uses your daily AI allowance and is recorded in the audit log.")) return;
    setBusy(true);
    try {
      const task = buildAiTask({ question: q, moduleName: p.moduleName, file: p.file, excerpts: related });
      const run = await p.api.createRun(p.project, task);
      add({ from: "ai", runId: run.id, status: run.status, text: "" });
      if (canApprove) {
        await p.api.decide(run.id, true);
        await p.api.enqueue(run.id);
        updateAi(run.id, { status: "approved" });
        p.onStatus("AI request approved and queued");
      } else {
        updateAi(run.id, { status: "awaiting_approval", text: "Your request is waiting for an owner, admin or reviewer to approve it in the Agents tab." });
        p.onStatus("AI request created — waiting for approval");
      }
      void poll(run.id);
    } catch (e) {
      p.onStatus(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  const suggestions = suggestedTopics(topics, p.module, 5);

  return <>
    <button className="assistant-fab primary" aria-expanded={open} aria-controls="aepx-assistant"
      onClick={() => setOpen(o => !o)} title="Help and AI assistant">{open ? "Close assistant" : "Assistant"}</button>
    {open && <section id="aepx-assistant" className="assistant-drawer" role="dialog" aria-label="AEP-X Assistant">
      <header className="assistant-head">
        <strong>Assistant</strong><span className="muted small"> · {p.moduleName}</span>
        <a className="small" href="/help/aepx-help.md" target="_blank" rel="noopener noreferrer">All help</a>
        <button className="icon" aria-label="Close assistant" onClick={() => setOpen(false)}>×</button>
      </header>
      <div className="assistant-log" aria-live="polite">
        {!messages.length && <div>
          <p className="muted small">Ask anything about AEP-X. Help answers are instant and free{ai.ok ? "; Ask AI uses your AI allowance" : ""}.</p>
          {suggestions.map(t => <button key={t.module + t.title} className="link-button" onClick={() => askHelp(t.title)}>{t.title}</button>)}
          {!topics.length && <p className="muted small">Loading help…</p>}
        </div>}
        {messages.map(m => m.from === "you"
          ? <p key={m.id} className="msg you">{m.text}</p>
          : m.from === "help"
            ? <div key={m.id} className="msg help">
                {m.topics.length
                  ? m.topics.map(t => <details key={t.module + t.title} open={t === m.topics[0]}>
                      <summary>{t.title} <span className="muted small">· {t.moduleTitle}</span></summary>
                      <p className="help-body">{t.body}</p></details>)
                  : <p>No help page matches that yet.</p>}
                {ai.ok
                  ? <button disabled={busy} onClick={() => void askAi(m.question, m.topics)}>Ask AI instead</button>
                  : <p className="muted small">{ai.reason}</p>}
              </div>
            : <div key={m.id} className="msg ai">
                <p className="muted small">AI · {m.status.replace(/_/g, " ")}</p>
                {!m.text && !FINAL_STATUSES.has(m.status) && <p className="working">Working on it…</p>}
                {m.text && splitResult(m.text).map((b, i) => b.kind === "text"
                  ? <p key={i} className="help-body">{b.text}</p>
                  : <div key={i}><pre><code>{b.code}</code></pre>
                      {b.file && p.onSaveFile && <button onClick={() => void p.onSaveFile!(b.file!, b.code.endsWith("\n") ? b.code : b.code + "\n")
                        .then(() => p.onStatus("Saved " + b.file)).catch(e => p.onStatus(String(e)))}>Save {b.file} to project</button>}</div>)}
              </div>)}
        <div ref={endRef} />
      </div>
      <form className="assistant-input" onSubmit={e => { e.preventDefault(); askHelp(); }}>
        <label className="sr-only" htmlFor="assistant-q">Your question</label>
        <input id="assistant-q" value={question} maxLength={1500} placeholder="e.g. How do I import a zip?"
          onChange={e => setQuestion(e.target.value)} autoFocus />
        <button className="primary" disabled={question.trim().length < 2}>Ask</button>
      </form>
    </section>}
  </>;
}
