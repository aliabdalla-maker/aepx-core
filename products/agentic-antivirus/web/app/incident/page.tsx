"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, ReadAloud, Sev, Status, useApi } from "../../components/ui";
import { IncidentAgents, IncidentPlaybooks } from "../../components/AgentPanels";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

export default function Incident() {
  const { t, locale } = useI18n();
  const [id, setId] = useState<string | null>(null);
  useEffect(() => { setId(new URLSearchParams(location.search).get("id")); }, []);
  const d = useApi<any>(id ? `/v1/incidents/${id}` : null);
  const [useLlm, setUseLlm] = useState(false);
  const inv = d.data?.investigations?.[0];
  const f = inv?.findings;
  const summary = f ? [
    ...f.facts.map((x: any) => x.statement),
    ...f.hypotheses.map((x: any) => t("incident.hypothesisLine", { confidence: x.confidence, statement: x.statement })),
    ...f.missing_evidence.map((x: string) => t("incident.missingLine", { item: x }))].join(". ") : "";
  return (
    <Shell>
      <Status error={d.error} loading={!d.data} />
      {d.data && <>
        <h1>{d.data.incident.title}</h1>
        <p className="lede"><Sev s={d.data.incident.severity} /> {d.data.incident.status}, opened {formatDateTime(d.data.incident.created_at, locale)}</p>
        <div className="row">
          <label style={{ margin: 0, display: "flex", gap: ".4rem" }}><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
            {t("ui.include_the_language_model_if_your")}</label>
          <Act className="primary" label={t("incident.investigate")} run={() => api(`/v1/incidents/${id}/investigate`, { body: { use_llm: useLlm, language: locale } })} onDone={d.reload} />
        </div>
        {id && <IncidentAgents id={id} onChange={d.reload} />}
        {id && <IncidentPlaybooks id={id} />}

        {f && <>
          <h2>{t("incident.facts")}</h2>
          <ReadAloud text={summary} />
          <ul>{f.facts.map((x: any, i: number) => <li key={i}>{x.statement} <span className="ref">({x.evidence_refs.join(", ")})</span></li>)}</ul>
          <h2>{t("incident.hypotheses")}</h2>
          {f.hypotheses.length ? <ul className="hyps">{f.hypotheses.map((x: any, i: number) => <li key={i} className="finding-h">
            {x.statement} <span className="chip">{x.confidence} confidence</span>
            {x.evidence_refs.length > 0 && <span className="ref"> ({x.evidence_refs.join(", ")})</span>}</li>)}</ul> : <p>{t("ui.none")}</p>}
          <h2>{t("incident.missing")}</h2>
          {f.missing_evidence.length ? <ul>{f.missing_evidence.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul> : <p>{t("ui.none_reported")}</p>}
          {f.impact && (f.impact.confirmed.length + f.impact.suspected.length > 0) && <>
            <h2>{t("ui.affected_services")}</h2>
            <p>Confirmed: {f.impact.confirmed.join(", ") || "none"}. Suspected: {f.impact.suspected.join(", ") || "none"}.</p></>}
          <h2>{t("incident.recommendations")}</h2>
          <table><thead><tr><th>{t("ui.action")}</th><th>{t("ui.why")}</th><th>{t("ui.status")}</th></tr></thead>
            <tbody>{f.recommendations.map((r: any, i: number) => <tr key={i}><td>{r.action_type}</td><td>{r.rationale}</td>
              <td>{r.status === "proposed" ? <Link href="/approvals">{t("ui.waiting_for_approval")}</Link> : r.status}</td></tr>)}</tbody></table>
          <p className="lede">Engine: {inv.engine}{f.model_status ? `. Model: ${f.model_status}` : ""}.</p>
        </>}

        <h2>{t("incident.timeline")}</h2>
        <ol className="timeline">{d.data.timeline.map((e: any) => (
          <li key={e.ref} className={e.type}>
            <strong>{formatDateTime(e.at, locale)}</strong> {e.type === "alert" && <Sev s={e.severity} />}{" "}
            {e.summary ?? e.kind ?? `${e.signal}: ${e.category}`} {e.device && <>on {e.device}</>}
            {e.data?.simulation && <span className="chip sim">{t("common.simulation")}</span>}
            <div className="ref">{e.ref}{e.rule ? `, rule ${e.rule}` : ""}{e.data?.cmdline ? `, ${e.data.cmdline}` : ""}</div>
          </li>))}</ol>

        {d.data.recovery.length > 0 && <>
          <h2>{t("ui.recovery")}</h2>
          <table><thead><tr><th>{t("ui.step")}</th><th>{t("ui.status")}</th><th>{t("ui.backup_verified")}</th><th>{t("ui.return_to_service")}</th></tr></thead>
            <tbody>{d.data.recovery.map((r: any) => <tr key={r.id}><td>{r.step}</td><td>{r.status}</td>
              <td>{r.backup_verified === null ? t("common.unknown") : r.backup_verified ? t("common.yes") : t("common.no")}</td>
              <td>{r.step === "return_to_service" ? (r.return_to_service_approved_by ? t("incident.approved") :
                <Act label={t("ui.approve_return_to_service")} run={() => api(`/v1/recovery/${r.id}/approve-return`, { method: "POST" })} onDone={d.reload} />) : ""}</td></tr>)}</tbody></table>
        </>}
      </>}
    </Shell>);
}
