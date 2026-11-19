"use client";
import Link from "next/link";
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
        <option value="">{t("ui.all")}</option>{["critical", "high", "medium", "low"].map((s) => <option key={s}>{s}</option>)}</select></label>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("alerts.title")}</th><th>{t("alerts.severity")}</th><th>{t("devices.hostname")}</th><th>{t("alerts.rule")}</th>
        <th>{t("ui.response")}</th><th>{t("alerts.detected")}</th><th>{t("ui.status")}</th></tr></thead>
        <tbody>{(d.data ?? []).map((a) => <tr key={a.id}>
          <td>{a.incident_id ? <Link href={`/incident?id=${a.incident_id}`}>{a.title}</Link> : a.title}</td><td><Sev s={a.severity} /></td>
          <td>{a.hostname ?? "—"}</td><td>{a.rule_id} v{a.rule_version}</td><td>{a.action_taken ?? "alert only"}</td>
          <td>{formatDateTime(a.detected_at, locale)}</td>
          <td>{a.status === "new" ? <Act label={t("ui.mark_false_positive")} run={() => api(`/v1/alerts/${a.id}`, { method: "PATCH", body: { status: "false_positive" } })} onDone={d.reload} /> : a.status}</td>
        </tr>)}</tbody></table>

      <h2>{t("alerts.report")}</h2>
      <form className="form" onSubmit={async (e) => { e.preventDefault();
        await api("/v1/reports", { body: { kind, description: desc, url: url || undefined } }); setDesc(""); setUrl(""); d.reload(); }}>
        <label>{t("ui.what_is_it")}<select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="file">{t("ui.a_file")}</option><option value="email">{t("ui.an_email")}</option><option value="url">{t("ui.a_website_link")}</option><option value="other">{t("ui.something_else")}</option></select></label>
        <label>{t("ui.describe_what_happened")}<textarea rows={3} minLength={3} required value={desc} onChange={(e) => setDesc(e.target.value)} /></label>
        <Dictate onText={(s) => setDesc((v) => (v ? v + " " : "") + s)} />
        {kind !== "file" && <label>{t("ui.link_if_there_is_one")}<input type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></label>}
        <button className="primary">{t("ui.send_report")}</button>
      </form>
    </Shell>);
}
