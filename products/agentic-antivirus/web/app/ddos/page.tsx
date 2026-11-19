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
      <p className="lede">{t("ui.traffic_floods_are_absorbed_by_your")}</p>
      <Freshness at={st.at} />
      <Status error={cov.error} loading={!cov.data} />
      {cov.data && <div className="stats">
        <div><strong>{cov.data.accounted_pct ?? "—"}%</strong><span>public endpoints accounted for ({cov.data.accounted_for}/{cov.data.public_endpoints})</span></div>
        <div><strong>{st.data?.mitigation_active.length ?? 0}</strong><span>{t("ui.assets_under_active_mitigation")}</span></div>
        <div><strong>{st.data?.affected_assets.length ?? 0}</strong><span>{t("ui.assets_with_alerts_in_24_hours")}</span></div>
      </div>}
      {cov.data?.uncovered.length > 0 && <p className="banner warn">Not covered: {cov.data.uncovered.map((u: any) => u.value).join(", ")}</p>}

      <h2>{t("ui.provider_alerts_24_hours")}</h2>
      <table><thead><tr><th>{t("ui.received")}</th><th>{t("ui.signal")}</th><th>{t("ui.type")}</th><th>{t("alerts.severity")}</th><th>{t("ui.asset")}</th><th>{t("ui.impact")}</th><th>{t("ui.notified_after")}</th></tr></thead>
        <tbody>{(st.data?.recent_alerts ?? []).map((x: any) => <tr key={x.id}><td>{formatDateTime(x.received_at, locale)}</td><td>{x.signal_kind}
          {x.simulation === "true" && <span className="chip sim">{t("common.simulation")}</span>}</td><td>{x.category}</td><td><Sev s={x.severity} /></td>
          <td>{x.asset}</td><td>{x.confirmed ? t("ddos.confirmed") : t("ddos.suspected")}</td>
          <td>{x.notified_at ? `${Math.round((+new Date(x.notified_at) - +new Date(x.received_at)) / 1000)} s` : "—"}</td></tr>)}</tbody></table>

      <h2>{t("ui.public_endpoints")}</h2>
      <table><thead><tr><th>{t("ui.endpoint")}</th><th>{t("ui.service")}</th><th>{t("ui.owner")}</th><th>{t("ui.provider")}</th><th>{t("ui.mitigation")}</th><th>{t("ui.capacity")}</th><th>{t("ui.exception")}</th></tr></thead>
        <tbody>{(assets.data ?? []).map((x) => <tr key={x.id}><td>{x.value}{!x.covered && <span className="chip sim">{t("ui.uncovered")}</span>}</td>
          <td>{x.service}</td><td>{x.service_owner}</td><td>{x.provider ?? "—"}</td><td>{x.mitigation_policy ?? "—"}</td>
          <td>{x.capacity_assumptions ?? "—"}</td><td>{x.exception_note ?? ""}</td></tr>)}</tbody></table>
      <div className="form">
        <div className="row"><select aria-label={t("ui.kind")} value={a.kind} onChange={set("kind")}><option value="hostname">{t("ui.hostname")}</option><option value="ip">{t("ui.ip_address")}</option><option value="dns_zone">{t("ui.dns_zone")}</option></select>
          <input aria-label={t("ui.endpoint")} placeholder={t("ui.shop_example_com")} value={a.value} onChange={set("value")} /></div>
        {(["service", "service_owner", "provider", "mitigation_policy", "capacity_assumptions", "exception_note"] as const).map((k) =>
          <label key={k}>{k.replace(/_/g, " ")}<input value={a[k]} onChange={set(k)} /></label>)}
        <Act className="primary" label={t("ui.save_endpoint")} run={() => api("/v1/assets", { body: Object.fromEntries(Object.entries(a).map(([k, v]) => [k, v || null])) })} onDone={() => { assets.reload(); cov.reload(); }} />
      </div>

      <h2>{t("ui.service_objectives")}</h2>
      <table><thead><tr><th>{t("ui.service")}</th><th>{t("ui.availability")}</th><th>{t("ui.p95_latency")}</th><th>{t("ui.legitimate_request_success")}</th></tr></thead>
        <tbody>{(slos.data ?? []).map((s) => <tr key={s.id}><td>{s.service}</td><td>{s.availability_pct}%</td><td>{s.latency_p95_ms} ms</td><td>{s.success_rate_pct}%</td></tr>)}</tbody></table>

      <h2>{t("ui.traffic_restrictions")}</h2>
      <table><thead><tr><th>{t("ui.service")}</th><th>{t("ui.control")}</th><th>{t("nav.settings")}</th><th>{t("ui.status")}</th><th /></tr></thead>
        <tbody>{(tps.data ?? []).map((p) => <tr key={p.id}><td>{p.service}</td><td>{p.control}</td><td><code>{JSON.stringify(p.config)}</code></td>
          <td>{p.status}{p.standing ? " (standing)" : ""}</td>
          <td><Act label={t("ui.roll_back")} run={() => api(`/v1/traffic-policies/${p.id}/rollback`, { method: "POST" })} onDone={tps.reload} /></td></tr>)}</tbody></table>
    </Shell>);
}
