"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

const BOOL = ["on_access", "on_execute", "on_download", "auto_quarantine_known", "behaviour_rules", "block_suspicious_scripts",
  "isolation_allowed", "tamper_protection", "url_protection", "collect_file_contents"] as const;
const LABEL: Record<string, string> = { on_access: "policy.option.on_access", on_execute: "policy.option.on_execute", on_download: "policy.option.on_download", auto_quarantine_known: "policy.option.auto_quarantine_known", behaviour_rules: "policy.option.behaviour_rules", block_suspicious_scripts: "policy.option.block_suspicious_scripts", isolation_allowed: "policy.option.isolation_allowed", tamper_protection: "policy.option.tamper_protection", url_protection: "policy.option.url_protection", collect_file_contents: "policy.option.collect_file_contents" };

export default function Policies() {
  const { t } = useI18n();
  const { locale } = useI18n();
  const d = useApi<any[]>("/v1/policies");
  const sch = useApi<any[]>("/v1/scan-schedules");
  const ex = useApi<any[]>("/v1/exclusions");
  const [name, setName] = useState("default");
  const [body, setBody] = useState<Record<string, any>>({ on_access: true, on_execute: true, on_download: true,
    auto_quarantine_known: true, behaviour_rules: true, isolation_allowed: true, tamper_protection: true,
    removable_media: "audit", event_buffer_mb: 64, allowed_management_hosts: [] });
  const [cron, setCron] = useState("0 2 * * 0");
  const [exVal, setExVal] = useState("");
  const [exReason, setExReason] = useState("");
  return (
    <Shell>
      <h1>{t("nav.policies")}</h1>
      <p className="lede">{t("ui.each_publish_creates_a_new_signed")}</p>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("ui.name")}</th><th>{t("ui.version")}</th><th>{t("ui.published")}</th></tr></thead>
        <tbody>{(d.data ?? []).map((p) => <tr key={p.id}><td>{p.name}</td><td>{p.version}</td><td>{formatDateTime(p.created_at, locale)}</td></tr>)}</tbody></table>

      <h2>{t("ui.publish_a_policy_version")}</h2>
      <div className="form">
        <label>{t("ui.name")}<input value={name} pattern="[a-z0-9_-]+" onChange={(e) => setName(e.target.value)} /></label>
        {BOOL.map((k) => <label key={k} style={{ display: "flex", gap: ".5rem", fontWeight: 400 }}>
          <input type="checkbox" checked={!!body[k]} onChange={(e) => setBody({ ...body, [k]: e.target.checked })} />{t(LABEL[k])}</label>)}
        <label>{t("ui.removable_media")}<select value={body.removable_media} onChange={(e) => setBody({ ...body, removable_media: e.target.value })}>
          <option value="allow">{t("ui.allow")}</option><option value="audit">{t("ui.allow_and_scan")}</option><option value="block">{t("ui.block")}</option></select></label>
        <label>{t("ui.offline_event_buffer_mb")}<input type="number" min={1} max={4096} value={body.event_buffer_mb}
          onChange={(e) => setBody({ ...body, event_buffer_mb: Number(e.target.value) })} /></label>
        <label>{t("ui.management_hosts_kept_reachable_during_isolation")} <span className="hint">{t("ui.comma_separated")}</span>
          <input value={body.allowed_management_hosts.join(",")} onChange={(e) => setBody({ ...body,
            allowed_management_hosts: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
        <Act className="primary" label={t("ui.publish_signed_version")} run={() => api("/v1/policies", { body: { name, body } })} onDone={d.reload} />
      </div>

      <h2>{t("ui.scheduled_scans")}</h2>
      <ul>{(sch.data ?? []).map((s) => <li key={s.id}>{s.scan_type} scan for {s.policy_name}: <code>{s.cron}</code>{" "}
        <Act label={t("ui.remove")} run={() => api(`/v1/scan-schedules/${s.id}`, { method: "DELETE" })} onDone={sch.reload} /></li>)}</ul>
      <div className="row"><label style={{ margin: 0 }}>{t("ui.schedule_cron")}<input value={cron} onChange={(e) => setCron(e.target.value)} /></label>
        <Act label={t("ui.add_weekly_full_scan")} run={() => api("/v1/scan-schedules", { body: { policy_name: name, scan_type: "full", cron } })} onDone={sch.reload} /></div>

      <h2>{t("ui.exclusions")}</h2>
      <p className="lede">{t("ui.an_administrator_must_give_a_reason")}</p>
      <ul>{(ex.data ?? []).map((x) => <li key={x.id}>{x.kind}: <code>{x.value}</code> — {x.reason}{" "}
        <Act label={t("ui.remove")} run={() => api(`/v1/exclusions/${x.id}`, { method: "DELETE" })} onDone={ex.reload} /></li>)}</ul>
      <div className="row"><label style={{ margin: 0 }}>{t("ui.path_pattern")}<input value={exVal} onChange={(e) => setExVal(e.target.value)} /></label>
        <label style={{ margin: 0 }}>{t("quarantine.reason")}<input value={exReason} onChange={(e) => setExReason(e.target.value)} /></label>
        <Act label={t("ui.add_exclusion")} run={() => api("/v1/actions", { body: { action_type: "add_exclusion", targets: ["tenant"],
          params: { kind: "path", value: exVal }, reason: exReason } })} onDone={ex.reload} /></div>
    </Shell>);
}
