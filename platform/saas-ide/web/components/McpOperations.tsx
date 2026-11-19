"use client";
import { useCallback, useEffect, useState } from "react";
import { PANEL_TEXT, panelStateFromError, type PanelState } from "../lib/signin";
type Execution = { approval_id: string; run_id: string; state: string; created_at: string; completed_at: string | null };
type Props = { request: (url: string, method?: string, body?: unknown) => Promise<any>; enabled: boolean };
export default function McpOperations({ request, enabled }: Props) {
  const [rows, setRows] = useState<Execution[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  // Never "no data" unless the server actually answered with none.
  const [state, setState] = useState<PanelState>(enabled ? "loading" : "signed-out");
  const [message, setMessage] = useState("");
  const [receipt, setReceipt] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState<Record<string, string>>({});
  const refresh = useCallback(async () => {
    if (!enabled) { setState("signed-out"); setRows([]); setCounts({}); return; }
    setState("loading");
    try {
      const [data, metrics] = await Promise.all([
        request("/api/v1/operations/mcp/executions"),
        request("/api/v1/operations/mcp/metrics")
      ]);
      const list: Execution[] = Array.isArray(data?.executions) ? data.executions : [];
      setRows(list);
      setCounts(metrics?.counts ?? {});
      setState(list.length || Object.keys(metrics?.counts ?? {}).length ? "ready" : "empty");
      setMessage("");
    } catch (e) { setRows([]); setCounts({}); setState(panelStateFromError(e)); }
  }, [enabled, request]);
  useEffect(() => { void refresh(); }, [refresh]);
  async function reconcile(id: string) {
    if (!receipt[id]?.trim() || !outcome[id]) return;
    if (!window.confirm("Confirm signed provider receipt and outcome? This will be audited.")) return;
    try {
      await request("/api/v1/operations/mcp/executions/" + encodeURIComponent(id) + "/reconcile", "POST",
        { outcome: outcome[id], signed_receipt: receipt[id].trim() });
      setReceipt(prev => ({...prev, [id]: ""}));
      await refresh();
    } catch (e) {
      const s = panelStateFromError(e);
      setMessage(s === "denied" ? "Reconciliation denied: owner or administrator access is required."
        : s === "unavailable" ? "Reconciliation not sent: the operations service is unreachable."
        : "Reconciliation rejected: the receipt is invalid or the execution is no longer uncertain.");
    }
  }
  return <section aria-label="MCP execution operations" style={{padding:16,borderTop:"1px solid #555"}}>
    <h3>MCP execution operations <small>(owner/admin only, no automatic replay)</small></h3>
    {enabled && <button disabled={state === "loading"} onClick={() => void refresh()}>Refresh executions</button>}
    {state === "ready"
      ? <p>States: {Object.entries(counts).map(([k,v]) => k + ": " + v).join(" · ") || "none recorded"}</p>
      : <p className={state === "denied" || state === "failed" ? "warn" : "muted"} data-state={state}>{PANEL_TEXT[state]}</p>}
    <div role="status">{message}</div>
    {rows.map(row => <article key={row.approval_id} style={{borderTop:"1px solid #555",padding:8}}>
      <strong>{row.state}</strong> · Run {row.run_id} · Approval {row.approval_id}
      {row.state === "outcome_unknown" && <div>
        <label>Verified outcome <select aria-label={"Outcome " + row.approval_id}
          value={outcome[row.approval_id] || ""} onChange={e => setOutcome(p => ({...p,[row.approval_id]:e.target.value}))}>
          <option value="">Select</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option>
        </select></label>
        <textarea aria-label={"Signed receipt " + row.approval_id} rows={2} maxLength={4096}
          placeholder="Provider-signed evidence receipt" value={receipt[row.approval_id] || ""}
          onChange={e => setReceipt(p => ({...p,[row.approval_id]:e.target.value}))} style={{width:"100%"}} />
        <button disabled={!outcome[row.approval_id] || !receipt[row.approval_id]?.trim()}
          title="Choose the verified outcome and paste the provider-signed receipt first."
          onClick={() => void reconcile(row.approval_id)}>Verify and reconcile</button>
      </div>}
    </article>)}
  </section>;
}
