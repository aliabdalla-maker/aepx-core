"use client";
import { useCallback, useEffect, useState } from "react";
type Execution = { approval_id: string; run_id: string; state: string; created_at: string; completed_at: string | null };
type Props = { request: (url: string, method?: string, body?: unknown) => Promise<any>; enabled: boolean };
export default function McpOperations({ request, enabled }: Props) {
  const [rows, setRows] = useState<Execution[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [message, setMessage] = useState("");
  const [receipt, setReceipt] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState<Record<string, string>>({});
  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const [data, metrics] = await Promise.all([
        request("/api/v1/operations/mcp/executions"),
        request("/api/v1/operations/mcp/metrics")
      ]);
      setRows(data.executions);
      setCounts(metrics.counts);
      setMessage("");
    } catch (e) { setMessage("MCP operations unavailable or administrator access required"); }
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
    } catch (e) { setMessage("Reconciliation denied: receipt invalid, unauthorized, or execution not uncertain"); }
  }
  return <section aria-label="MCP execution operations" style={{padding:16,borderTop:"1px solid #555"}}>
    <h3>MCP execution operations <small>(owner/admin only, no automatic replay)</small></h3>
    <button disabled={!enabled} onClick={() => void refresh()}>Refresh executions</button>
    <p>States: {Object.entries(counts).map(([k,v]) => k + ": " + v).join(" · ") || "No execution metrics"}</p>
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
          onClick={() => void reconcile(row.approval_id)}>Verify and reconcile</button>
      </div>}
    </article>)}
  </section>;
}
