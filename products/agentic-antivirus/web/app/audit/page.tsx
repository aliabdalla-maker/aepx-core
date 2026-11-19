"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Status, useApi } from "../../components/ui";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";
import { API_BASE, session } from "../../lib/api";

export default function Audit() {
  const { t } = useI18n();
  const { locale } = useI18n();
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const d = useApi<any[]>("/v1/audit", { action: action || undefined, limit: 100, offset: page * 100 });
  const v = useApi<any>("/v1/audit/verify");
  const exportKpis = async (fmt: string) => {
    const r = await fetch(`${API_BASE}/v1/kpis/export?fmt=${fmt}`, { headers: { Authorization: `Bearer ${session.token()}`, "X-Tenant-Id": session.tenant() ?? "" } });
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = `kpis.${fmt}`; a.click();
  };
  return (
    <Shell>
      <h1>{t("ui.audit_trail")}</h1>
      {v.data && <p className={v.data.valid ? "banner" : "banner warn"} role="status">
        {v.data.valid ? t("audit.intact", { n: v.data.entries }) : t("audit.broken", { id: v.data.first_break_id })}</p>}
      <div className="row">
        <label style={{ margin: 0 }}>{t("ui.action")}<input value={action} onChange={(e) => { setAction(e.target.value); setPage(0); }} placeholder={t("ui.action_approve")} /></label>
        {["csv", "json", "pdf"].map((f) => <button key={f} onClick={() => exportKpis(f)}>Export KPIs as {f.toUpperCase()}</button>)}
      </div>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("ui.when")}</th><th>{t("ui.who")}</th><th>{t("ui.action")}</th><th>{t("ui.target")}</th><th>{t("ui.detail")}</th></tr></thead>
        <tbody>{(d.data ?? []).map((e) => <tr key={e.id}><td>{formatDateTime(e.at, locale)}</td><td>{e.actor}</td><td>{e.action}</td>
          <td><code>{e.target}</code></td><td><code style={{ overflowWrap: "anywhere" }}>{JSON.stringify(e.detail).slice(0, 240)}</code></td></tr>)}</tbody></table>
      <div className="row"><button disabled={page === 0} onClick={() => setPage(page - 1)}>{t("common.previous")}</button>
        <button disabled={(d.data?.length ?? 0) < 100} onClick={() => setPage(page + 1)}>{t("common.next")}</button></div>
    </Shell>);
}
