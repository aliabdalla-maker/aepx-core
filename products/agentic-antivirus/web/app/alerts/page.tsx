"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Dictate, Freshness, Sev, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

export default function Alerts() {
  const { t, locale } = useI18n();
  const [severity, setSeverity] = useState("");
  const d = useApi<any[]>("/v1/alerts", { severity, limit: 200 });
  const [kind, setKind] = useState("file");
  const [desc, setDesc] = useState("");
  const [url, setUrl] = useState("");
  return (
    <Shell>
      <h1>{t("nav.alerts")}</h1>
      <Freshness at={d.at} />
      <label style={{ maxWidth: "14rem" }}>{t("alerts.severity")}<select value={severity} onChange={(e) => setSeverity(e.target.value)}>
        <option value="">All</option>{["critical", "high", "medium", "low"].map((s) => <option key={s}>{s}</option>)}</select></label>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("alerts.title")}</th><th>{t("alerts.severity")}</th><th>{t("devices.hostname")}</th><th>{t("alerts.rule")}</th>
        <th>Response</th><th>{t("alerts.detected")}</th><th>Status</th></tr></thead>
        <tbody>{(d.data ?? []).map((a) => <tr key={a.id}>
          <td>{a.incident_id ? <a href={`/incident?id=${a.incident_id}`}>{a.title}</a> : a.title}</td><td><Sev s={a.severity} /></td>
          <td>{a.hostname ?? "—"}</td><td>{a.rule_id} v{a.rule_version}</td><td>{a.action_taken ?? "alert only"}</td>
          <td>{formatDateTime(a.detected_at, locale)}</td>
          <td>{a.status === "new" ? <Act label="Mark false positive" run={() => api(`/v1/alerts/${a.id}`, { method: "PATCH", body: { status: "false_positive" } })} onDone={d.reload} /> : a.status}</td>
        </tr>)}</tbody></table>

      <h2>{t("alerts.report")}</h2>
      <form className="form" onSubmit={async (e) => { e.preventDefault();
        await api("/v1/reports", { body: { kind, description: desc, url: url || undefined } }); setDesc(""); setUrl(""); d.reload(); }}>
        <label>What is it?<select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="file">A file</option><option value="email">An email</option><option value="url">A website link</option><option value="other">Something else</option></select></label>
        <label>Describe what happened<textarea rows={3} minLength={3} required value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
        <Dictate onText={(s) => setDesc((v) => (v ? v + " " : "") + s)} />
        {kind !== "file" && <label>Link, if there is one<input type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></label>}
        <button className="primary">Send report</button>
      </form>
    </Shell>);
}
