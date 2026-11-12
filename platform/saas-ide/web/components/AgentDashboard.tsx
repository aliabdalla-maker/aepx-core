"use client";
import { useCallback, useEffect, useState } from "react";
type Run = { id: string; status: string; model_route: string; task: string; attempts: number; result: string };
type Props = { project: string; request: (url: string, method?: string, body?: unknown) => Promise<any> };
export default function AgentDashboard({ project, request }: Props) {
  const [task, setTask] = useState("");
  const [provider, setProvider] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => {
    if (!project) { setRuns([]); return; }
    try { setRuns(await request("/api/v1/projects/" + project + "/agent-runs")); }
    catch (error) { setMessage(String(error)); }
  }, [project, request]);
  useEffect(() => { void refresh(); }, [refresh]);
  async function submit() {
    if (!project || task.trim().length < 5) return;
    try {
      await request("/api/v1/agent-runs", "POST", {
        project_id: project, task: task.trim(), ...(provider ? { preferred_provider: provider } : {})
      });
      setTask(""); setMessage("Plan submitted; human approval required."); await refresh();
    } catch (error) { setMessage(String(error)); }
  }
  async function action(id: string, kind: "approve" | "reject" | "cancel" | "retry") {
    try {
      const suffix = kind === "approve" || kind === "reject"
        ? "/decision?approved=" + (kind === "approve") : "/" + kind;
      await request("/api/v1/agent-runs/" + id + suffix, "POST");
      await refresh();
    } catch (error) { setMessage(String(error)); }
  }
  return <section aria-label="Agent supervisor" style={{padding:16,borderTop:"1px solid #555"}}>
    <h3>Agent supervisor <small>(approval-gated)</small></h3>
    <textarea aria-label="Agent task" value={task} onChange={e=>setTask(e.target.value)}
      placeholder="Describe a software engineering task" maxLength={4000} rows={3} style={{width:"100%"}}/>
    <label> Provider <select value={provider} onChange={e=>setProvider(e.target.value)}>
      <option value="">Auto</option><option value="oci">OCI</option><option value="openai">OpenAI</option>
      <option value="anthropic">Anthropic</option><option value="gemini">Gemini</option>
    </select></label>
    <button disabled={!project || task.trim().length < 5} onClick={submit}>Create plan</button>
    <button disabled={!project} onClick={()=>void refresh()}>Refresh</button>
    <div role="status">{message}</div>
    {runs.map(r=><article key={r.id} style={{borderTop:"1px solid #555",padding:8}}>
      <strong>{r.task}</strong> — {r.status} · {r.model_route} · attempts {r.attempts}
      {r.result && <pre style={{whiteSpace:"pre-wrap"}}>{r.result}</pre>}
      <div>
        {r.status==="awaiting_approval" && <>
          <button onClick={()=>void action(r.id,"approve")}>Approve</button>
          <button onClick={()=>void action(r.id,"reject")}>Reject</button>
        </>}
        {["awaiting_approval","approved","running","failed"].includes(r.status) &&
          <button onClick={()=>void action(r.id,"cancel")}>Cancel</button>}
        {r.status==="failed" && r.attempts<2 &&
          <button onClick={()=>void action(r.id,"retry")}>Request retry</button>}
      </div>
    </article>)}
  </section>;
}
