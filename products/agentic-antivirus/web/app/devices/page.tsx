"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, AdSlot, Freshness, Status, useApi } from "../../components/ui";
import { api, apiUrl } from "../../lib/api";
import { ThisComputer } from "../../components/ThisComputer";
import { useI18n } from "../../lib/i18n";
import { formatRelative, localeIncludes } from "../../lib/format";

export default function Devices() {
  const { t, locale } = useI18n();
  const d = useApi<any[]>("/v1/devices");
  const pol = useApi<any[]>("/v1/policies");
  const lic = useApi("/v1/licence");
  const [token, setToken] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const names = Array.from(new Set((pol.data ?? []).map((p) => p.name)));
  return (
    <Shell>
      <h1>{t("nav.devices")}</h1>
      <ThisComputer onChange={d.reload} />
      <Freshness at={d.at} />
      <div className="row">
        <label style={{ margin: 0 }}>{t("common.search")}<input value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <Act label={t("devices.enrol")} run={() => api("/v1/enrollment-tokens", { body: { max_uses: 1, expires_hours: 24 } })}
          onDone={(r: any) => setToken(r.token)} />
      </div>
      {token && <div className="banner" role="status"><p>{t("devices.runWithin")}</p>
        <code style={{ overflowWrap: "anywhere" }}>aav-agent enrol --url {apiUrl()} --token {token}</code>
          <p>{t("ui.get_the_agent_for_windows_mac")} <a href="https://softwareequality.com/agentic-antivirus-download#dl-agent">{t("ui.download_page")}</a>.</p></div>}
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("devices.hostname")}</th><th>{t("devices.os")}</th><th>{t("devices.status")}</th><th>{t("ui.definitions")}</th>
        <th>{t("devices.policy")}</th><th>{t("devices.last_seen")}</th><th>{t("devices.issues")}</th><th>{t("ui.scan")}</th></tr></thead>
        <tbody>{d.data && d.data.filter((x) => localeIncludes(x.hostname, q, locale)).length === 0 &&
          <tr><td colSpan={8}>{d.data.length === 0 ? t("security.noDevices") : t("common.none")}</td></tr>}
          {(d.data ?? []).filter((x) => localeIncludes(x.hostname, q, locale)).map((x) => <tr key={x.id}>
          <td>{x.hostname}{x.criticality === "critical" && <span className="chip">{t("ui.critical")}</span>}
            {x.isolation_state === "isolated" && <span className="chip sim">isolated until {formatRelative(x.isolation_expires_at, locale)}</span>}</td>
          <td>{x.os} {x.os_version}</td>
          <td className={x.protection_status === "protected" ? "ok" : "sev-high"}>{x.protection_status}</td>
          <td>{x.definitions_version ?? "none"}</td>
          <td><select aria-label={`Policy for ${x.hostname}`} value={x.policy_name ?? ""} onChange={async (e) => {
            await api(`/v1/devices/${x.id}`, { method: "PATCH", body: { policy_name: e.target.value } }); d.reload(); }}>
            {names.map((n) => <option key={n}>{n}</option>)}</select> v{x.applied_policy_version ?? "?"}</td>
          <td>{formatRelative(x.last_seen_at, locale)}</td>
          <td>{x.issues.map((i: string) => <span key={i} className="chip">{t(`devices.issue.${i}`)}</span>)}</td>
          <td><Act label={t("ui.quick_scan")} run={() => api("/v1/scans", { body: { device_ids: [x.id], scan_type: "quick" } })} /></td>
        </tr>)}</tbody></table>
      {lic.data && <AdSlot placement="device_list_banner" rate={lic.data.ad_rate} />}
    </Shell>);
}
