"use client";
import { useEffect, useState } from "react";
import { api, session } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { formatRelative } from "../lib/format";
import { Act } from "./ui";

export type ActionRequest = { id: string; action_type: string; targets: string[]; params: Record<string, unknown>;
  reason: string; proposed_by: string; status: string; created_at: string; incident_id: string | null;
  policy_decision: { mode?: string; risk?: string; multi_endpoint?: boolean; reason?: string } };

const HUMAN: Record<string, string> = {
  terminate_process: "Stop a process", isolate_device: "Isolate a device from the network",
  release_isolation: "Release a device from isolation", restore_file: "Restore a quarantined file",
  add_exclusion: "Add a permanent exclusion", quarantine_file: "Quarantine a file", run_scan: "Scan devices",
  collect_metadata: "Collect device metadata", suspend_account: "Suspend a user account",
  revoke_sessions: "Sign a user out everywhere", apply_traffic_policy: "Apply a traffic restriction",
  rollback_traffic_policy: "Roll back a traffic restriction", rollback_update: "Roll back an update",
};

export function DecisionCard({ a, names, onChange }: { a: ActionRequest; names: Record<string, string>; onChange: () => void }) {
  const { t, locale } = useI18n();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(i); }, []);
  const ttl = Number(process.env.NEXT_PUBLIC_APPROVAL_TTL_MINUTES ?? 60);
  const params = Object.entries(a.params).map(([k, v]) => `${k} ${String(v)}`).join(", ") || "none";
  return (
    <article className="decision" aria-labelledby={`d-${a.id}`}>
      <div>
        <h3 id={`d-${a.id}`}>{HUMAN[a.action_type] ?? a.action_type}</h3>
        {a.proposed_by.startsWith("ai:") && <span className="chip">{t("actions.proposed_by_ai")}</span>}
        {a.policy_decision.multi_endpoint && <span className="chip">{a.targets.length} devices</span>}
        <dl className="binds">
          <dt>Targets</dt><dd>{a.targets.map((x) => names[x] ?? x).join(", ")}</dd>
          <dt>Details</dt><dd>{params}</dd>
          <dt>Organisation</dt><dd>{names[session.tenant() ?? ""] ?? "this organisation"}</dd>
          <dt>Reason</dt><dd>{a.reason || "none given"}</dd>
          <dt>Risk</dt><dd>{a.policy_decision.risk ?? "—"}</dd>
          <dt>Requested</dt><dd>{formatRelative(a.created_at, locale, now)}</dd>
        </dl>
        <p className="expiry">If approved, the approval is valid for {ttl} minutes and only for these targets.</p>
      </div>
      <div className="actions">
        {a.status === "proposed" && <Act className="decide" label={t("actions.approve")}
          run={() => api(`/v1/actions/${a.id}/approve`, { body: {} })} onDone={onChange} />}
        {a.status === "approved" && <Act className="decide" label={t("actions.dispatch")}
          run={() => api(`/v1/actions/${a.id}/dispatch`, { method: "POST" })} onDone={onChange} />}
        <Act label={t("actions.deny")} run={() => api(`/v1/actions/${a.id}/deny`, { body: { reason: "" } })} onDone={onChange} />
        {a.incident_id && <a href={`/incident?id=${a.incident_id}`}>Open incident</a>}
      </div>
    </article>);
}
