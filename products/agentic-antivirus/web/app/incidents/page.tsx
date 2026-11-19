"use client";
import Link from "next/link";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { AdSlot, Freshness, Sev, Status, useApi } from "../../components/ui";
import { useI18n } from "../../lib/i18n";
import { formatRelative, localeIncludes } from "../../lib/format";

export default function Incidents() {
  const { t, locale } = useI18n();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const d = useApi<any[]>("/v1/incidents", { status, limit: 50, offset: page * 50 });
  const lic = useApi("/v1/licence");
  const rows = (d.data ?? []).filter((i) => localeIncludes(i.title, q, locale));
  return (
    <Shell>
      <h1>{t("nav.incidents")}</h1>
      <Freshness at={d.at} />
      <div className="row">
        <label style={{ margin: 0 }}>{t("common.search")}<input value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label style={{ margin: 0 }}>{t("ui.status")}<select value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
          <option value="">{t("ui.all")}</option>{["open", "investigating", "contained", "recovering", "resolved"].map((s) => <option key={s}>{s}</option>)}
        </select></label>
      </div>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("ui.incident")}</th><th>{t("alerts.severity")}</th><th>{t("ui.status")}</th><th>{t("ui.category")}</th><th>{t("nav.alerts")}</th><th>{t("ui.updated")}</th></tr></thead>
        <tbody>{rows.map((i) => <tr key={i.id}><td><Link href={`/incident?id=${i.id}`}>{i.title}</Link></td><td><Sev s={i.severity} /></td>
          <td>{i.status}</td><td>{i.category}</td><td>{i.alert_count}</td><td>{formatRelative(i.updated_at, locale)}</td></tr>)}</tbody></table>
      <div className="row"><button disabled={page === 0} onClick={() => setPage(page - 1)}>{t("common.previous")}</button>
        <button disabled={(d.data?.length ?? 0) < 50} onClick={() => setPage(page + 1)}>{t("common.next")}</button></div>
      {lic.data && <AdSlot placement="incident_list_banner" rate={lic.data.ad_rate} />}
    </Shell>);
}
