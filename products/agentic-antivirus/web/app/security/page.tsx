"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Empty, Freshness, Sev, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

type Ratio = { numerator: number; denominator: number; value: number | "N/A"; unknown?: number };

const STATE_CLASS: Record<string, string> = { protected: "ok", degraded: "warn", unprotected: "bad", unknown: "muted" };

function Kpi({ label, r }: { label: string; r?: Ratio }) {
  const { t } = useI18n();
  if (!r) return null;
  return <div><strong>{r.value === "N/A" ? t("common.na") : `${r.value}%`}</strong>
    <span>{label} ({r.numerator}/{r.denominator}){r.unknown ? ` · ${t("security.unknownCount", { n: r.unknown })}` : ""}</span></div>;
}

function Times({ label, v }: { label: string; v?: { median: number | null; p95: number | null; n: number; open_cases?: number } }) {
  const { t } = useI18n();
  if (!v) return null;
  return <div><strong>{v.median == null ? t("common.unavailable") : `${v.median} s`}</strong>
    <span>{label}: {t("security.p95", { v: v.p95 ?? "—" })} · n={v.n}{v.open_cases ? ` · ${t("security.openCases", { n: v.open_cases })}` : ""}</span></div>;
}

export default function Security() {
  const { t, locale } = useI18n();
  const dash = useApi<any>("/v1/security/dashboard");
  const gaps = useApi<any[]>("/v1/security/gaps");
  const jobs = useApi<any[]>("/v1/scan-jobs");
  const segs = useApi<any[]>("/v1/network/segments");
  const [scan, setScan] = useState({ device: "", type: "full", paths: "" });
  const [seg, setSeg] = useState({ name: "", cidr: "" });
  const k = dash.data?.kpis;
  const rec = dash.data?.recovery;
  const reload = () => { dash.reload(); gaps.reload(); jobs.reload(); segs.reload(); };
  return (
    <Shell>
      <h1>{t("nav.security")}</h1>
      <p className="lede">{t("security.lede")}</p>
      <Freshness at={dash.at} />
      <Status error={dash.error} loading={!dash.data} />
      {k && <>
        <div className="stats" aria-label={t("security.states")}>
          {(["protected", "degraded", "unprotected", "unknown"] as const).map((s) =>
            <div key={s} className={STATE_CLASS[s]}><strong>{k.states[s]}</strong><span>{t(`security.state.${s}`)}</span></div>)}
        </div>
        <h2>{t("security.kpis")}</h2>
        <div className="stats">
          <Kpi label={t("security.kpi.coverage")} r={k.endpoint_protection_coverage} />
          <Kpi label={t("security.kpi.fullScan")} r={k.full_scan_coverage} />
          <Kpi label={t("security.kpi.reliability")} r={k.scan_execution_reliability} />
          <Kpi label={t("security.kpi.network")} r={k.network_visibility} />
          <Kpi label={t("security.kpi.freshness")} r={k.signature_freshness} />
          <Kpi label={t("security.kpi.quality")} r={k.detection_quality} />
          <Kpi label={t("security.kpi.ddos")} r={k.ddos_resilience} />
          <Times label={t("security.kpi.detect")} v={k.detection_time_seconds} />
          <Times label={t("security.kpi.contain")} v={k.containment_time_seconds} />
          <div><strong>{k.gap_backlog.open}</strong><span>{t("security.kpi.gaps", { overdue: k.gap_backlog.overdue,
            closed: k.gap_backlog.verified_closures_30d })}</span></div>
        </div>
        <p className="hint">{t("security.zeroNote")}</p>
        {k.scan_execution_reliability.breakdown && <p className="hint">{t("security.jobOutcomes")}: {Object.entries(k.scan_execution_reliability.breakdown)
          .map(([s, n]) => `${t(`scan.status.${s}`)} ${n}`).join(" · ") || "—"}</p>}
      </>}

      <h2>{t("security.devices")}</h2>
      {dash.data?.devices?.length === 0 && <Empty>{t("security.noDevices")}</Empty>}
      {dash.data?.devices?.length > 0 && <table><thead><tr><th>{t("devices.hostname")}</th><th>{t("security.state")}</th>
        <th>{t("security.reasons")}</th><th>{t("security.lastSeen")}</th><th>{t("security.lastFullScan")}</th>
        <th>{t("security.posture")}</th></tr></thead>
        <tbody>{dash.data.devices.map((d: any) => <tr key={d.id}><td>{d.hostname}</td>
          <td><span className={`chip ${STATE_CLASS[d.state]}`}>{t(`security.state.${d.state}`)}</span></td>
          <td>{d.reasons.join("; ") || "—"}</td><td>{d.last_seen_at ? formatDateTime(d.last_seen_at, locale) : t("common.never")}</td>
          <td>{d.last_full_scan ? formatDateTime(d.last_full_scan, locale) : t("common.never")}</td>
          <td>{t("security.postureLine", {
            enc: d.posture?.disk_encryption == null ? t("common.unknown") : d.posture.disk_encryption ? t("common.on") : t("common.off"),
            fw: d.posture?.firewall == null ? t("common.unknown") : d.posture.firewall ? t("common.on") : t("common.off") })}</td></tr>)}</tbody></table>}

      <h2>{t("security.gaps")}</h2>
      <Status error={gaps.error} loading={!gaps.data} />
      {gaps.data?.length === 0 && <Empty>{t("security.noGaps")}</Empty>}
      {(gaps.data?.length ?? 0) > 0 && <table><thead><tr><th>{t("security.gap.subject")}</th><th>{t("security.gap.expected")}</th>
        <th>{t("security.gap.observed")}</th><th>{t("security.gap.evidence")}</th><th>{t("alerts.severity")}</th>
        <th>{t("security.gap.owner")}</th><th>{t("security.gap.due")}</th><th>{t("security.gap.fix")}</th><th>{t("security.gap.retest")}</th></tr></thead>
        <tbody>{gaps.data!.map((g) => <tr key={g.id}><td>{g.subject_label}</td><td>{g.expected_control}</td><td>{g.observed_state}</td>
          <td>{g.last_evidence_at ? formatDateTime(g.last_evidence_at, locale) : t("common.unknown")}</td><td><Sev s={g.severity} /></td>
          <td>{g.owner}</td><td>{g.due_date}{g.overdue && <span className="chip bad">{t("security.overdue")}</span>}</td>
          <td>{g.proposed_fix}</td><td>{t(`security.retest.${g.retest_status}`)}</td></tr>)}</tbody></table>}
      <Act label={t("security.reevaluate")} run={() => api("/v1/security/gaps/evaluate", { method: "POST" })} onDone={reload} />

      <h2>{t("security.scans")}</h2>
      <div className="form row">
        <select aria-label={t("devices.hostname")} value={scan.device} onChange={(e) => setScan({ ...scan, device: e.target.value })}>
          <option value="">{t("security.chooseDevice")}</option>
          {(dash.data?.devices ?? []).map((d: any) => <option key={d.id} value={d.id}>{d.hostname}</option>)}</select>
        <select aria-label={t("security.scanType")} value={scan.type} onChange={(e) => setScan({ ...scan, type: e.target.value })}>
          {["quick", "full", "targeted", "on_demand"].map((s) => <option key={s} value={s}>{t(`scan.type.${s}`)}</option>)}</select>
        {scan.type === "targeted" && <input aria-label={t("security.paths")} placeholder={t("security.pathsHint")} value={scan.paths}
          onChange={(e) => setScan({ ...scan, paths: e.target.value })} />}
        <Act className="primary" label={t("security.startScan")} run={() => api("/v1/scan-jobs", { body: {
          device_ids: scan.device ? [scan.device] : (dash.data?.devices ?? []).map((d: any) => d.id), scan_type: scan.type,
          paths: scan.paths ? scan.paths.split(/[,\n]/).map((s) => s.trim()).filter(Boolean) : [] } })} onDone={reload} />
      </div>
      <table><thead><tr><th>{t("devices.hostname")}</th><th>{t("security.scanType")}</th><th>{t("common.status")}</th>
        <th>{t("security.files")}</th><th>{t("security.detections")}</th><th>{t("security.coverageGaps")}</th>
        <th>{t("security.engine")}</th><th>{t("security.started")}</th><th /></tr></thead>
        <tbody>{(jobs.data ?? []).map((j) => <tr key={j.id}><td>{j.hostname}</td><td>{t(`scan.type.${j.scan_type}`)}</td>
          <td>{t(`scan.status.${j.status}`)}</td><td>{j.files_scanned}{j.archives_scanned ? ` (+${j.archives_scanned} ${t("security.archives")})` : ""}</td>
          <td>{j.detections}</td><td>{Object.entries(j.gaps ?? {}).map(([g, n]) => `${t(`scan.gap.${g}`)} ${n}`).join(", ") || "—"}</td>
          <td>{j.engine_version ?? "—"}</td><td>{formatDateTime(j.created_at, locale)}</td>
          <td>{["queued", "running"].includes(j.status) && <Act label={t("security.cancel")} confirm={t("security.cancelConfirm")}
            run={() => api(`/v1/scan-jobs/${j.id}/cancel`, { method: "POST" })} onDone={reload} />}</td></tr>)}</tbody></table>

      <h2>{t("security.network")}</h2>
      <table><thead><tr><th>{t("security.segment")}</th><th>{t("ui.cidr")}</th><th>{t("security.visibility")}</th><th>{t("security.lastTelemetry")}</th>
        <th>{t("security.assets")}</th></tr></thead>
        <tbody>{(segs.data ?? []).map((s) => <tr key={s.id}><td>{s.name}</td><td><code>{s.cidr}</code></td>
          <td><span className={`chip ${s.visibility === "monitored" ? "ok" : "bad"}`}>{t(`security.vis.${s.visibility}`)}</span></td>
          <td>{s.last_telemetry_at ? formatDateTime(s.last_telemetry_at, locale) : t("common.never")}</td><td>{s.assets}</td></tr>)}</tbody></table>
      <div className="form row">
        <input aria-label={t("security.segment")} placeholder={t("security.segmentName")} value={seg.name} onChange={(e) => setSeg({ ...seg, name: e.target.value })} />
        <input aria-label={t("ui.cidr")} placeholder="10.0.0.0/24" value={seg.cidr} onChange={(e) => setSeg({ ...seg, cidr: e.target.value })} />
        <Act label={t("security.addSegment")} run={() => api("/v1/network/segments", { body: seg })} onDone={reload} />
      </div>

      {rec && <>
        <h2>{t("security.recovery")}</h2>
        <div className="stats">
          <Kpi label={t("recovery.kpi.removal")} r={rec.verified_removal_rate} />
          <Kpi label={t("recovery.kpi.scans")} r={rec.post_mitigation_scan_coverage} />
          <Kpi label={t("recovery.kpi.mitigation")} r={rec.mitigation_verification_rate} />
          <Kpi label={t("recovery.kpi.recurrence")} r={rec.recurrence_rate} />
          <Kpi label={t("recovery.kpi.return")} r={rec.safe_return_to_service_rate} />
          <div><strong>{rec.time_to_verified_eradication_hours.median ?? t("common.unavailable")}{rec.time_to_verified_eradication_hours.median != null ? " h" : ""}</strong>
            <span>{t("recovery.kpi.eradication", { n: rec.time_to_verified_eradication_hours.n, open: rec.time_to_verified_eradication_hours.unresolved })}</span></div>
        </div>
        <p className="hint">{t("recovery.note", { q: rec.verified_removal_rate.quarantine_only, r: rec.verified_removal_rate.reimage })}</p>
      </>}
    </Shell>
  );
}
