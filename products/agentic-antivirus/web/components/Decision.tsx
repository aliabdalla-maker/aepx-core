"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, session } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { formatRelative } from "../lib/format";
import { Act } from "./ui";

export type ActionRequest = { id: string; action_type: string; targets: string[]; params: Record<string, unknown>;
  reason: string; proposed_by: string; status: string; created_at: string; incident_id: string | null;
  policy_decision: { mode?: string; risk?: string; multi_endpoint?: boolean; reason?: string } };

const HUMAN: Record<string, string> = { terminate_process: "action.name.terminate_process", isolate_device: "action.name.isolate_device", release_isolation: "action.name.release_isolation", restore_file: "action.name.restore_file", add_exclusion: "action.name.add_exclusion", quarantine_file: "action.name.quarantine_file", run_scan: "action.name.run_scan", collect_metadata: "action.name.collect_metadata", suspend_account: "action.name.suspend_account", revoke_sessions: "action.name.revoke_sessions", apply_traffic_policy: "action.name.apply_traffic_policy", rollback_traffic_policy: "action.name.rollback_traffic_policy", rollback_update: "action.name.rollback_update" };

export function DecisionCard({ a, names, onChange }: { a: ActionRequest; names: Record<string, string>; onChange: () => void }) {
  const { t, locale } = useI18n();
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const i = setInterval(() => setNow(Date.now()), 15000); return () => clearInterval(i); }, []);
  const ttl = Number(process.env.NEXT_PUBLIC_APPROVAL_TTL_MINUTES ?? 60);
  const params = Object.entries(a.params).map(([k, v]) => `${k} ${String(v)}`).join(", ") || "none";
  return (
    <article className="decision" aria-labelledby={`d-${a.id}`}>
      <div>
        <h3 id={`d-${a.id}`}>{HUMAN[a.action_type] ? t(HUMAN[a.action_type]) : a.action_type}</h3>
        {a.proposed_by.startsWith("ai:") && <span className="chip">{t("actions.proposed_by_ai")}</span>}
        {a.policy_decision.multi_endpoint && <span className="chip">{a.targets.length} devices</span>}
        <dl className="binds">
          <dt>{t("ui.targets")}</dt><dd>{a.targets.map((x) => names[x] ?? x).join(", ")}</dd>
          <dt>{t("ui.details")}</dt><dd>{params}</dd>
          <dt>{t("auth.organisation")}</dt><dd>{names[session.tenant() ?? ""] ?? "this organisation"}</dd>
          <dt>{t("quarantine.reason")}</dt><dd>{a.reason || "none given"}</dd>
          <dt>{t("ui.risk")}</dt><dd>{a.policy_decision.risk ?? "—"}</dd>
          <dt>{t("ui.requested")}</dt><dd>{formatRelative(a.created_at, locale, now)}</dd>
        </dl>
        <p className="expiry">If approved, the approval is valid for {ttl} minutes and only for these targets.</p>
      </div>
      <div className="actions">
        {a.status === "proposed" && <Act className="decide" label={t("actions.approve")}
          run={() => api(`/v1/actions/${a.id}/approve`, { body: {} })} onDone={onChange} />}
        {a.status === "approved" && <Act className="decide" label={t("actions.dispatch")}
          run={() => api(`/v1/actions/${a.id}/dispatch`, { method: "POST" })} onDone={onChange} />}
        <Act label={t("actions.deny")} run={() => api(`/v1/actions/${a.id}/deny`, { body: { reason: "" } })} onDone={onChange} />
        {a.incident_id && <Link href={`/incident?id=${a.incident_id}`}>{t("ui.open_incident")}</Link>}
      </div>
    </article>);
}
