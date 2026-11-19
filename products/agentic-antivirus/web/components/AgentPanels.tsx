"use client";
import { useState } from "react";
import { api, describeError } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { Dictate, ReadAloud } from "./ui";

/** Engine label: which provider answered (Claude, self-hosted model or rules) — shown on every agent output. */
export function EngineChip({ engine }: { engine: string }) {
  const { t } = useI18n();
  const kind = engine.startsWith("llm:anthropic") ? "claude" : engine.startsWith("llm:ollama") ? "local" : "rules";
  return <span className="chip" title={engine}>{t(`ai.engine.${kind}`)}</span>;
}

/** Assistant (playbook "assistant" 1.0.0): read-only answers from the tenant's posture, incidents and gaps. */
export function Assistant() {
  const { t, locale } = useI18n();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [a, setA] = useState<{ answer: string; engine: string; citations: string[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ask = async () => {
    setBusy(true); setErr(null);
    try { setA(await api("/v1/assistant/ask", { body: { question: q, language: locale } })); }
    catch (e) { setErr(describeError(e)); }
    finally { setBusy(false); }
  };
  return (
    <section aria-labelledby="assistant-h" className="card">
      <h2 id="assistant-h">{t("ai.assistant")}</h2>
      <p className="hint">{t("ai.assistantHint")}</p>
      <div className="row">
        <input aria-label={t("ai.question")} placeholder={t("ai.questionPlaceholder")} value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && q.trim().length > 1) ask(); }} />
        <Dictate onText={(s) => setQ(s)} />
        <button className="primary" disabled={busy || q.trim().length < 2} onClick={ask}>{busy ? t("common.working") : t("ai.ask")}</button>
      </div>
      {err && <p className="banner bad" role="alert">{err}</p>}
      {a && <div aria-live="polite"><p>{a.answer} <EngineChip engine={a.engine} /></p><ReadAloud text={a.answer} />
        {a.citations.length > 0 && <p className="hint">{t("ai.citations")}: {a.citations.join(", ")}</p>}</div>}
    </section>);
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
