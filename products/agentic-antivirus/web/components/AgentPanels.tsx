"use client";
import { useState } from "react";
import { api, describeError } from "../lib/api";
import { useI18n } from "../lib/i18n";

/** Engine label: which provider answered (Claude, self-hosted model or rules) — shown on every agent output. */
export function EngineChip({ engine }: { engine: string }) {
  const { t } = useI18n();
  const kind = engine.startsWith("llm:anthropic") ? "claude" : engine.startsWith("llm:ollama") ? "local" : "rules";
  return <span className="chip" title={engine}>{t(`ai.engine.${kind}`)}</span>;
}

/** Triage + remediation plan for one incident. The plan only files proposals that wait for approval. */
export function IncidentAgents({ id, onChange }: { id: string; onChange: () => void }) {
  const { t, locale } = useI18n();
  const [tri, setTri] = useState<any>(null);
  const [plan, setPlan] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (fn: () => Promise<void>) => { setErr(null); try { await fn(); } catch (e) { setErr(describeError(e)); } };
  return (
    <section aria-labelledby="agents-h">
      <h2 id="agents-h">{t("ai.agents")}</h2>
      <div className="row">
        <button onClick={() => run(async () => setTri(await api(`/v1/incidents/${id}/triage`, { body: { language: locale } })))}>
          {t("ai.triage")}</button>
        <button onClick={() => run(async () => { setPlan(await api(`/v1/incidents/${id}/remediation-plan`, { body: { language: locale } })); onChange(); })}>
          {t("ai.plan")}</button>
      </div>
      {err && <p className="banner bad" role="alert">{err}</p>}
      {tri && <div aria-live="polite"><p><strong>{t("ai.summary")}:</strong> {tri.summary} <EngineChip engine={tri.engine} /></p>
        <p>{t("ai.suggestedSeverity")}: {tri.suggested_severity}</p>
        <ul>{tri.key_points.map((k: any, i: number) => <li key={i}>{k.statement} <span className="ref">{k.evidence_refs.join(", ")}</span></li>)}</ul>
        {tri.unsupported_points_dropped > 0 && <p className="hint">{t("ai.dropped", { n: tri.unsupported_points_dropped })}</p>}</div>}
      {plan && <div aria-live="polite"><p>{t("ai.planNote")} <EngineChip engine={plan.engine} /></p>
        <table><thead><tr><th>{t("ai.action")}</th><th>{t("ai.targets")}</th><th>{t("ai.why")}</th><th>{t("common.status")}</th></tr></thead>
          <tbody>{plan.steps.map((s: any, i: number) => <tr key={i}><td>{s.action_type}</td><td>{s.targets.join(", ")}</td>
            <td>{s.rationale}</td><td>{s.status}</td></tr>)}</tbody></table></div>}
    </section>);
}

/** §3C playbook catalogue: which playbooks apply to this incident and whether each completion criterion is met. */
export function IncidentPlaybooks({ id }: { id: string }) {
  const { t } = useI18n();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api(`/v1/harness/incidents/${id}/playbooks`).then(setD).catch((e) => setErr(describeError(e)));
  return (
    <section aria-labelledby="pb-h">
      <h2 id="pb-h">{t("response.playbooks")}</h2>
      <button onClick={load}>{d ? t("common.refresh") : t("response.checkPlaybooks")}</button>
      {err && <p className="banner bad" role="alert">{err}</p>}
      {d && d.playbooks.map((pb: any) => (
        <div key={pb.playbook} className="card">
          <h3>{t(`response.pb.${pb.playbook}`)} <span className="hint">v{pb.version}</span>{" "}
            <span className={`chip ${pb.complete ? "ok" : "warn"}`}>{pb.complete ? t("response.complete") : t("response.incomplete")}</span></h3>
          <ul>{pb.criteria.map((c: any) => <li key={c.criterion}>
            <span className={`chip ${c.status === "PASS" ? "ok" : c.status === "FAIL" ? "bad" : "muted"}`}>{c.status}</span> {c.criterion}
            <div className="hint">{c.evidence}</div></li>)}</ul>
        </div>))}
    </section>);
}
