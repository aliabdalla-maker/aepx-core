"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

const BOOL = ["on_access", "on_execute", "on_download", "auto_quarantine_known", "behaviour_rules", "block_suspicious_scripts",
  "isolation_allowed", "tamper_protection", "url_protection", "collect_file_contents"] as const;
const LABEL: Record<string, string> = { on_access: "Scan files when they are opened or written", on_execute: "Scan programs when they start",
  on_download: "Scan downloads", auto_quarantine_known: "Quarantine known malware automatically", behaviour_rules: "Watch for suspicious behaviour",
  block_suspicious_scripts: "Block suspicious scripts", isolation_allowed: "Allow network isolation", tamper_protection: "Protect the agent from changes",
  url_protection: "Warn about known malicious links", collect_file_contents: "Collect file contents for investigation (off by default)" };

export default function Policies() {
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
      <h1>Policies</h1>
      <p className="lede">Each publish creates a new signed version. Devices keep enforcing the last verified version while offline.</p>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>Name</th><th>Version</th><th>Published</th></tr></thead>
        <tbody>{(d.data ?? []).map((p) => <tr key={p.id}><td>{p.name}</td><td>{p.version}</td><td>{formatDateTime(p.created_at, locale)}</td></tr>)}</tbody></table>

      <h2>Publish a policy version</h2>
      <div className="form">
        <label>Name<input value={name} pattern="[a-z0-9_-]+" onChange={(e) => setName(e.target.value)} /></label>
        {BOOL.map((k) => <label key={k} style={{ display: "flex", gap: ".5rem", fontWeight: 400 }}>
          <input type="checkbox" checked={!!body[k]} onChange={(e) => setBody({ ...body, [k]: e.target.checked })} />{LABEL[k]}</label>)}
        <label>Removable media<select value={body.removable_media} onChange={(e) => setBody({ ...body, removable_media: e.target.value })}>
          <option value="allow">Allow</option><option value="audit">Allow and scan</option><option value="block">Block</option></select></label>
        <label>Offline event buffer (MB)<input type="number" min={1} max={4096} value={body.event_buffer_mb}
          onChange={(e) => setBody({ ...body, event_buffer_mb: Number(e.target.value) })} /></label>
        <label>Management hosts kept reachable during isolation <span className="hint">Comma separated</span>
          <input value={body.allowed_management_hosts.join(",")} onChange={(e) => setBody({ ...body,
            allowed_management_hosts: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></label>
        <Act className="primary" label="Publish signed version" run={() => api("/v1/policies", { body: { name, body } })} onDone={d.reload} />
      </div>

      <h2>Scheduled scans</h2>
      <ul>{(sch.data ?? []).map((s) => <li key={s.id}>{s.scan_type} scan for {s.policy_name}: <code>{s.cron}</code>{" "}
        <Act label="Remove" run={() => api(`/v1/scan-schedules/${s.id}`, { method: "DELETE" })} onDone={sch.reload} /></li>)}</ul>
      <div className="row"><label style={{ margin: 0 }}>Schedule (cron)<input value={cron} onChange={(e) => setCron(e.target.value)} /></label>
        <Act label="Add weekly full scan" run={() => api("/v1/scan-schedules", { body: { policy_name: name, scan_type: "full", cron } })} onDone={sch.reload} /></div>

      <h2>Exclusions</h2>
      <p className="lede">An administrator must give a reason. The exclusion is recorded in the audit trail.</p>
      <ul>{(ex.data ?? []).map((x) => <li key={x.id}>{x.kind}: <code>{x.value}</code> — {x.reason}{" "}
        <Act label="Remove" run={() => api(`/v1/exclusions/${x.id}`, { method: "DELETE" })} onDone={ex.reload} /></li>)}</ul>
      <div className="row"><label style={{ margin: 0 }}>Path pattern<input value={exVal} onChange={(e) => setExVal(e.target.value)} /></label>
        <label style={{ margin: 0 }}>Reason<input value={exReason} onChange={(e) => setExReason(e.target.value)} /></label>
        <Act label="Add exclusion" run={() => api("/v1/actions", { body: { action_type: "add_exclusion", targets: ["tenant"],
          params: { kind: "path", value: exVal }, reason: exReason } })} onDone={ex.reload} /></div>
    </Shell>);
}
