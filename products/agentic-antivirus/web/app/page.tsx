"use client";
import Link from "next/link";
import { Shell } from "../components/Shell";
import { AdSlot, Freshness, Sev, Status, useApi } from "../components/ui";
import { DecisionCard, type ActionRequest } from "../components/Decision";
import { ThisComputer } from "../components/ThisComputer";
import { useI18n } from "../lib/i18n";
import { formatRelative } from "../lib/format";

export default function Dashboard() {
  const { t, locale } = useI18n();
  const k = useApi("/v1/kpis");
  const pending = useApi<ActionRequest[]>("/v1/actions", { status: "proposed" });
  const ready = useApi<ActionRequest[]>("/v1/actions", { status: "approved" });
  const inc = useApi<any[]>("/v1/incidents", { limit: 50 });
  const tenants = useApi<any[]>("/v1/tenants");
  const dev = useApi<any[]>("/v1/devices");
  const lic = useApi("/v1/licence");
  const names = Object.fromEntries([...(dev.data ?? []).map((d) => [d.id, d.hostname]),
    ...(tenants.data ?? []).map((x) => [x.tenant_id, x.tenant_name])]);
  const openInc = (inc.data ?? []).filter((i) => i.status !== "resolved").slice(0, 8);
  const decisions = [...(pending.data ?? []), ...(ready.data ?? [])];
  const reload = () => { pending.reload(); ready.reload(); k.reload(); };
  const issues = (dev.data ?? []).filter((d) => d.issues.length);
  return (
    <Shell pending={decisions.length}>
      <h1>{decisions.length ? t("dash.pending_approvals", { count: decisions.length }) : "Nothing is waiting for you"}</h1>
      <p className="lede">Automatic protection keeps running on every device. These are the actions that need a person to decide.</p>
      <ThisComputer onChange={() => { dev.reload(); k.reload(); }} />
      <Status error={pending.error} loading={!pending.data} />
      <section className="decisions" aria-label="Decisions waiting">
        {decisions.map((a) => <DecisionCard key={a.id} a={a} names={names} onChange={reload} />)}
      </section>

      <h2>Right now</h2>
      <Freshness at={k.at} />
      {k.data && <div className="stats">
        <div><strong>{k.data.devices.protected}/{k.data.devices.enrolled}</strong><span>devices fully protected</span></div>
        <div><strong>{k.data.alerts_24h.total}</strong><span>alerts in the last 24 hours</span></div>
        <div><strong>{k.data.incidents.open}</strong><span>open incidents</span></div>
        <div><strong>{k.data.devices.isolated}</strong><span>devices isolated</span></div>
        <div><strong>{k.data.critical_alert_publication_seconds.p95 == null ? "—" :
          `${Math.round(k.data.critical_alert_publication_seconds.p95)} s`}</strong><span>critical alert delivery (p95, 30 days)</span></div>
      </div>}

      <h2>Open incidents</h2>
      {openInc.length ? <table><thead><tr><th>Incident</th><th>{t("alerts.severity")}</th><th>Alerts</th><th>Updated</th></tr></thead>
        <tbody>{openInc.map((i) => <tr key={i.id}><td><Link href={`/incident?id=${i.id}`}>{i.title}</Link></td><td><Sev s={i.severity} /></td>
          <td>{i.alert_count}</td><td>{formatRelative(i.updated_at, locale)}</td></tr>)}</tbody></table>
        : <p>No open incidents.</p>}

      {issues.length > 0 && <>
        <h2>Devices that need attention</h2>
        <table><thead><tr><th>{t("devices.hostname")}</th><th>{t("devices.issues")}</th></tr></thead>
          <tbody>{issues.map((d) => <tr key={d.id}><td>{d.hostname}</td>
            <td>{d.issues.map((x: string) => <span key={x} className="chip">{t(`devices.issue.${x}`)}</span>)}</td></tr>)}</tbody></table>
      </>}
      {lic.data && <AdSlot placement="dashboard_banner" rate={lic.data.ad_rate} />}
    </Shell>);
}
