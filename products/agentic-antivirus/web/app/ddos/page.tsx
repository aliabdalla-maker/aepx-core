"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Freshness, Sev, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

export default function Ddos() {
  const { t, locale } = useI18n();
  const cov = useApi("/v1/ddos/coverage");
  const st = useApi("/v1/ddos/status");
  const assets = useApi<any[]>("/v1/assets");
  const slos = useApi<any[]>("/v1/service-objectives");
  const tps = useApi<any[]>("/v1/traffic-policies");
  const [a, setA] = useState({ kind: "hostname", value: "", service: "", service_owner: "", provider: "", mitigation_policy: "",
    capacity_assumptions: "", exception_note: "" });
  const set = (k: keyof typeof a) => (e: any) => setA({ ...a, [k]: e.target.value });
  return (
    <Shell>
      <h1>{t("nav.ddos")}</h1>
      <p className="lede">Traffic floods are absorbed by your upstream provider. Here you account for every public endpoint, watch provider alerts, and approve new traffic restrictions.</p>
      <Freshness at={st.at} />
      <Status error={cov.error} loading={!cov.data} />
      {cov.data && <div className="stats">
        <div><strong>{cov.data.accounted_pct ?? "—"}%</strong><span>public endpoints accounted for ({cov.data.accounted_for}/{cov.data.public_endpoints})</span></div>
        <div><strong>{st.data?.mitigation_active.length ?? 0}</strong><span>assets under active mitigation</span></div>
        <div><strong>{st.data?.affected_assets.length ?? 0}</strong><span>assets with alerts in 24 hours</span></div>
      </div>}
      {cov.data?.uncovered.length > 0 && <p className="banner warn">Not covered: {cov.data.uncovered.map((u: any) => u.value).join(", ")}</p>}

      <h2>Provider alerts (24 hours)</h2>
      <table><thead><tr><th>Received</th><th>Signal</th><th>Type</th><th>{t("alerts.severity")}</th><th>Asset</th><th>Impact</th><th>Notified after</th></tr></thead>
        <tbody>{(st.data?.recent_alerts ?? []).map((x: any) => <tr key={x.id}><td>{formatDateTime(x.received_at, locale)}</td><td>{x.signal_kind}
          {x.simulation === "true" && <span className="chip sim">{t("common.simulation")}</span>}</td><td>{x.category}</td><td><Sev s={x.severity} /></td>
          <td>{x.asset}</td><td>{x.confirmed ? "confirmed" : "suspected"}</td>
          <td>{x.notified_at ? `${Math.round((+new Date(x.notified_at) - +new Date(x.received_at)) / 1000)} s` : "—"}</td></tr>)}</tbody></table>

      <h2>Public endpoints</h2>
      <table><thead><tr><th>Endpoint</th><th>Service</th><th>Owner</th><th>Provider</th><th>Mitigation</th><th>Capacity</th><th>Exception</th></tr></thead>
        <tbody>{(assets.data ?? []).map((x) => <tr key={x.id}><td>{x.value}{!x.covered && <span className="chip sim">uncovered</span>}</td>
          <td>{x.service}</td><td>{x.service_owner}</td><td>{x.provider ?? "—"}</td><td>{x.mitigation_policy ?? "—"}</td>
          <td>{x.capacity_assumptions ?? "—"}</td><td>{x.exception_note ?? ""}</td></tr>)}</tbody></table>
      <div className="form">
        <div className="row"><select aria-label="Kind" value={a.kind} onChange={set("kind")}><option value="hostname">Hostname</option><option value="ip">IP address</option><option value="dns_zone">DNS zone</option></select>
          <input aria-label="Endpoint" placeholder="shop.example.com" value={a.value} onChange={set("value")} /></div>
        {(["service", "service_owner", "provider", "mitigation_policy", "capacity_assumptions", "exception_note"] as const).map((k) =>
          <label key={k}>{k.replace(/_/g, " ")}<input value={a[k]} onChange={set(k)} /></label>)}
        <Act className="primary" label="Save endpoint" run={() => api("/v1/assets", { body: Object.fromEntries(Object.entries(a).map(([k, v]) => [k, v || null])) })} onDone={() => { assets.reload(); cov.reload(); }} />
      </div>

      <h2>Service objectives</h2>
      <table><thead><tr><th>Service</th><th>Availability</th><th>p95 latency</th><th>Legitimate request success</th></tr></thead>
        <tbody>{(slos.data ?? []).map((s) => <tr key={s.id}><td>{s.service}</td><td>{s.availability_pct}%</td><td>{s.latency_p95_ms} ms</td><td>{s.success_rate_pct}%</td></tr>)}</tbody></table>

      <h2>Traffic restrictions</h2>
      <table><thead><tr><th>Service</th><th>Control</th><th>Settings</th><th>Status</th><th /></tr></thead>
        <tbody>{(tps.data ?? []).map((p) => <tr key={p.id}><td>{p.service}</td><td>{p.control}</td><td><code>{JSON.stringify(p.config)}</code></td>
          <td>{p.status}{p.standing ? " (standing)" : ""}</td>
          <td><Act label="Roll back" run={() => api(`/v1/traffic-policies/${p.id}/rollback`, { method: "POST" })} onDone={tps.reload} /></td></tr>)}</tbody></table>
    </Shell>);
}
