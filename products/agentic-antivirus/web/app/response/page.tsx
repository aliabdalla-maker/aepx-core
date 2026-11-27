"use client";
/**
 * Response console (deployment prompt §3C console views, §3D live console):
 * live state and runtime mode, feed freshness, approval queue, action receipts with independent verification,
 * harness KPIs, playbooks and production assertions. Drills and simulations are labelled everywhere.
 */
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Empty, Freshness, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

const LIFECYCLE_CLASS: Record<string, string> = { verified: "ok", failed: "bad", denied: "bad", expired: "muted",
  manual_reconciliation: "warn", verification_pending: "warn", running: "", queued: "", awaiting_approval: "warn" };
const FEED_CLASS: Record<string, string> = { Live: "ok", Stale: "warn", Unknown: "muted" };

function age(sec: number | null | undefined, t: (k: string, v?: any) => string) {
  if (sec == null) return t("common.unknown");
  if (sec < 120) return t("response.age.seconds", { n: sec });
  if (sec < 7200) return t("response.age.minutes", { n: Math.round(sec / 60) });
  return t("response.age.hours", { n: Math.round(sec / 3600) });
}

export default function Response() {
  const { t, locale } = useI18n();
  const live = useApi<any>("/v1/harness/live");
  const kpis = useApi<any>("/v1/harness/kpis");
  const queue = useApi<any>("/v1/harness/approvals");
  const [filter, setFilter] = useState("");
  const actions = useApi<any[]>("/v1/harness/actions", { lifecycle: filter || undefined });
  const playbooks = useApi<any>("/v1/harness/playbooks");
  const assertions = useApi<any[]>("/v1/harness/assertions");
  const pol = live.data?.runtime;
  const [edit, setEdit] = useState<{ mode: string; cohort: string[]; all: boolean; reason: string } | null>(null);
  const [rec, setRec] = useState<Record<string, { outcome: string; evidence: string }>>({});
  const [form, setForm] = useState({ requirement_id: "SEC-01", environment: "production", scope: "", artefact_digest: "",
    outcome: "PASS", coverage: "observe", evidence: "", owner: "" });
  const reload = () => { live.reload(); kpis.reload(); queue.reload(); actions.reload(); assertions.reload(); };
  const k = kpis.data;
  const endpoints = (live.data?.feeds ?? []).filter((f: any) => f.kind === "endpoint");
  const host: Record<string, string> = Object.fromEntries(endpoints.map((f: any) => [f.device_id, f.source.replace("endpoint:", "")]));
  const names = (ids: string[]) => ids.map((i) => host[i] ?? i).join(", ");

  return (
    <Shell pending={queue.data?.items?.length}>
      <h1>{t("nav.response")}</h1>
      <p className="lede">{t("response.lede")}</p>
      <Freshness at={live.at} />
      <Status error={live.error} loading={!live.data} />

      {live.data && <section aria-labelledby="live-h" className="card">
        <h2 id="live-h">{t("response.live")}</h2>
        <dl className="facts">
          <dt>{t("response.build")}</dt><dd><code>{live.data.deployment.build}</code> · {live.data.deployment.environment}</dd>
          <dt>{t("response.tenant")}</dt><dd>{live.data.tenant.name}</dd>
          <dt>{t("response.mode")}</dt><dd><span className={`chip ${pol.mode === "respond" ? "ok" : "warn"}`}>{t(`response.mode.${pol.mode}`)}</span>
            {" "}{t(`response.modeHint.${pol.mode}`)}</dd>
          <dt>{t("response.killSwitch")}</dt><dd>{pol.platform_kill_switch || pol.tenant_kill_switch
            ? <span className="chip bad">{t(pol.platform_kill_switch ? "response.kill.platform" : "response.kill.tenant")}</span>
            : t("common.off")}</dd>
          <dt>{t("response.cohort")}</dt><dd>{pol.respond_cohort.includes("*") ? t("response.cohortAll")
            : t("response.cohortCount", { n: pol.respond_cohort.length })}</dd>
          <dt>{t("response.coverage")}</dt><dd>{t("response.coverageLine", live.data.coverage)}</dd>
          <dt>{t("response.policyVersion")}</dt><dd><code>{live.data.deployment.policy_version}</code></dd>
          <dt>{t("response.observedAt")}</dt><dd>{formatDateTime(live.data.observed_at, locale)}</dd>
        </dl>
        {!edit && <button onClick={() => setEdit({ mode: pol.mode, cohort: pol.respond_cohort.filter((c: string) => c !== "*"),
          all: pol.respond_cohort.includes("*"), reason: "" })}>{t("response.change")}</button>}
        {edit && <div className="form">
          <fieldset><legend>{t("response.mode")}</legend>
            {["simulation", "observe", "respond"].map((m) => <label key={m} className="row">
              <input type="radio" name="mode" checked={edit.mode === m} onChange={() => setEdit({ ...edit, mode: m })} />
              {t(`response.mode.${m}`)} <span className="hint">{t(`response.modeHint.${m}`)}</span></label>)}
          </fieldset>
          {edit.mode === "respond" && <fieldset><legend>{t("response.cohort")}</legend>
            <label className="row"><input type="checkbox" checked={edit.all} onChange={(e) => setEdit({ ...edit, all: e.target.checked })} />
              {t("response.cohortAll")}</label>
            {!edit.all && endpoints.map((f: any) => <label key={f.device_id} className="row">
              <input type="checkbox" checked={edit.cohort.includes(f.device_id)} onChange={(e) => setEdit({ ...edit,
                cohort: e.target.checked ? [...edit.cohort, f.device_id] : edit.cohort.filter((c) => c !== f.device_id) })} />
              {f.source.replace("endpoint:", "")}</label>)}
          </fieldset>}
          <label>{t("response.reason")}<input value={edit.reason} onChange={(e) => setEdit({ ...edit, reason: e.target.value })} /></label>
          <div className="row">
            <Act className="primary" label={t("common.save")} run={() => api("/v1/harness/policy", { method: "PUT", body: {
              mode: edit.mode, respond_cohort: edit.all ? ["*"] : edit.cohort, reason: edit.reason } })}
              onDone={() => { setEdit(null); reload(); }} />
            <button onClick={() => setEdit(null)}>{t("common.cancel")}</button>
          </div>
        </div>}
        <div className="row">
          <Act className={pol.tenant_kill_switch ? "" : "danger"}
            label={pol.tenant_kill_switch ? t("response.killOff") : t("response.killOn")}
            confirm={pol.tenant_kill_switch ? undefined : t("response.killConfirm")}
            run={() => api("/v1/harness/policy", { method: "PUT", body: { kill_switch: !pol.tenant_kill_switch,
              reason: pol.tenant_kill_switch ? "kill switch released from console" : "kill switch engaged from console" } })}
            onDone={reload} />
        </div>
      </section>}

      <h2>{t("response.feeds")}</h2>
      {live.data?.feeds?.length === 0 && <Empty>{t("response.noFeeds")}</Empty>}
      {(live.data?.feeds?.length ?? 0) > 0 && <table><thead><tr><th>{t("response.source")}</th><th>{t("response.kind")}</th>
        <th>{t("common.status")}</th><th>{t("response.data")}</th><th>{t("response.lastEvent")}</th><th>{t("response.dataAge")}</th>
        <th>{t("response.respondEnabled")}</th></tr></thead>
        <tbody>{live.data.feeds.map((f: any) => <tr key={f.source}><td>{f.source}</td><td>{f.kind}</td>
          <td><span className={`chip ${FEED_CLASS[f.status]}`}>{t(`response.feed.${f.status}`)}</span></td>
          <td>{t(`response.dataKind.${f.data}`)}</td>
          <td>{f.last_event_at ? formatDateTime(f.last_event_at, locale) : t("common.never")}</td>
          <td>{age(f.data_age_seconds, t)}</td>
          <td>{f.kind === "endpoint" ? (f.respond_enabled ? t("common.yes") : t("common.no")) : "—"}</td></tr>)}</tbody></table>}

      <h2>{t("response.kpis")}</h2>
      <Status error={kpis.error} loading={!k} />
      {k && <>
        <div className="stats">
          <div><strong>{k.verified_action_success.value === "N/A" ? t("common.na") : `${k.verified_action_success.value}%`}</strong>
            <span>{t("response.kpi.verified", { n: k.verified_action_success.numerator, d: k.verified_action_success.denominator })}</span></div>
          <div><strong>{k.policy_denials.count}</strong><span>{t("response.kpi.denials")}</span></div>
          <div className={k.duplicate_side_effects.count ? "bad" : "ok"}><strong>{k.duplicate_side_effects.count}</strong>
            <span>{t("response.kpi.duplicates")}</span></div>
          <div className={k.approvals_overdue.count ? "warn" : undefined}><strong>{k.approvals_overdue.count}</strong>
            <span>{t("response.kpi.overdue", { waiting: k.approvals_overdue.waiting, sla: k.approvals_overdue.sla_minutes })}</span></div>
          <div><strong>{k.backlog_age_minutes.median ?? t("common.na")}</strong>
            <span>{t("response.kpi.backlog", { open: k.backlog_age_minutes.open, oldest: k.backlog_age_minutes.oldest ?? "—" })}</span></div>
          <div><strong>{k.feed_lag_seconds.median == null ? t("common.na") : `${k.feed_lag_seconds.median} s`}</strong>
            <span>{t("response.kpi.lag", { p95: k.feed_lag_seconds.p95 ?? "—", n: k.feed_lag_seconds.sample })}</span></div>
          <div><strong>{k.signal_to_triage_minutes.median == null ? t("common.na") : `${k.signal_to_triage_minutes.median} min`}</strong>
            <span>{t("response.kpi.triage", { p95: k.signal_to_triage_minutes.p95 ?? "—", n: k.signal_to_triage_minutes.sample,
              open: k.signal_to_triage_minutes.open_untriaged })}</span></div>
          <div><strong>{k.drill_and_simulation_requests}</strong><span>{t("response.kpi.drills")}</span></div>
        </div>
        <p className="hint">{t("response.kpiNote", { window: k.window })}</p>
      </>}

      <h2>{t("response.approvals")}</h2>
      {queue.data?.items?.length === 0 && <Empty>{t("response.noApprovals")}</Empty>}
      {(queue.data?.items?.length ?? 0) > 0 && <table><thead><tr><th>{t("ai.action")}</th><th>{t("ai.targets")}</th>
        <th>{t("response.reason")}</th><th>{t("response.waiting")}</th><th /></tr></thead>
        <tbody>{queue.data.items.map((a: any) => <tr key={a.id}><td>{t(`action.name.${a.action_type}`)}{a.drill && <span className="chip">{t("response.drill")}</span>}</td>
          <td>{names(a.targets)}</td><td>{a.reason}</td>
          <td>{age(a.age_seconds, t)}{a.overdue && <span className="chip warn">{t("security.overdue")}</span>}</td>
          <td><Act className="primary" label={t("response.approve")} run={() => api(`/v1/actions/${a.id}/approve`, { body: {} })} onDone={reload} />
            <Act label={t("response.deny")} run={() => api(`/v1/actions/${a.id}/deny`, { body: { reason: "denied from response console" } })}
              onDone={reload} /></td></tr>)}</tbody></table>}

      <h2>{t("response.receipts")}</h2>
      <label className="row">{t("response.filter")}
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">{t("response.filterAll")}</option>
          {Object.keys(LIFECYCLE_CLASS).map((l) => <option key={l} value={l}>{t(`response.lifecycle.${l}`)}</option>)}
        </select></label>
      <Status error={actions.error} loading={!actions.data} />
      {actions.data?.length === 0 && <Empty>{t("response.noActions")}</Empty>}
      {(actions.data?.length ?? 0) > 0 && <table><thead><tr><th>{t("ai.action")}</th><th>{t("response.lifecycle")}</th>
        <th>{t("response.mode")}</th><th>{t("response.dispatches")}</th><th>{t("response.verification")}</th><th>{t("response.updated")}</th></tr></thead>
        <tbody>{actions.data!.map((a) => <tr key={a.id}>
          <td>{t(`action.name.${a.action_type}`)}{a.drill && <span className="chip">{t("response.drill")}</span>}
            <div className="hint">{names(a.targets)}</div></td>
          <td><span className={`chip ${LIFECYCLE_CLASS[a.lifecycle] ?? ""}`}>{t(`response.lifecycle.${a.lifecycle}`)}</span>
            {a.lifecycle_reason && <div className="hint">{a.lifecycle_reason}</div>}
            {a.lifecycle === "manual_reconciliation" && <div className="form">
              <select aria-label={t("response.outcome")} value={rec[a.id]?.outcome ?? "not_executed"}
                onChange={(e) => setRec({ ...rec, [a.id]: { ...(rec[a.id] ?? { evidence: "" }), outcome: e.target.value } })}>
                <option value="not_executed">{t("response.notExecuted")}</option><option value="executed">{t("response.executed")}</option></select>
              <input aria-label={t("response.evidence")} placeholder={t("response.evidence")} value={rec[a.id]?.evidence ?? ""}
                onChange={(e) => setRec({ ...rec, [a.id]: { outcome: rec[a.id]?.outcome ?? "not_executed", evidence: e.target.value } })} />
              <Act label={t("response.reconcile")} run={() => api(`/v1/harness/actions/${a.id}/reconcile`, { body: {
                outcome: rec[a.id]?.outcome ?? "not_executed", evidence: rec[a.id]?.evidence ?? "" } })} onDone={reload} /></div>}</td>
          <td>{a.runtime_mode ? t(`response.mode.${a.runtime_mode}`) : "—"}</td>
          <td>{a.dispatches.map((d: any) => <div key={d.attempt}>#{d.attempt} {d.adapter}: {t(`response.dispatch.${d.state}`)}</div>)}</td>
          <td>{a.verifications.map((v: any, i: number) => <div key={i}>{t(`response.probe.${v.probe}`)}: {t(`response.check.${v.status}`)}
            {v.source ? ` (${t(`response.source.${v.source}`)})` : ""}</div>)}</td>
          <td>{formatDateTime(a.updated_at, locale)}</td></tr>)}</tbody></table>}

      <h2>{t("response.playbooks")}</h2>
      {playbooks.data && <>
        <table><thead><tr><th>{t("response.playbook")}</th><th>{t("response.trigger")}</th><th>{t("response.completion")}</th></tr></thead>
          <tbody>{Object.entries(playbooks.data.catalogue).map(([name, pb]: [string, any]) => <tr key={name}>
            <td>{t(`response.pb.${name}`)} <span className="hint">v{pb.version}</span></td><td>{pb.trigger}</td>
            <td><ul>{pb.completion.map((c: string) => <li key={c}>{c}</li>)}</ul></td></tr>)}</tbody></table>
        <h3>{t("response.pb.network_posture")}</h3>
        <ul>{playbooks.data.network_posture.map((c: any) => <li key={c.criterion}>
          <span className={`chip ${c.status === "PASS" ? "ok" : c.status === "FAIL" ? "bad" : "muted"}`}>{c.status}</span> {c.criterion}: {c.evidence}</li>)}</ul>
      </>}

      <h2>{t("response.assertions")}</h2>
      <p className="hint">{t("response.assertionsHint")}</p>
      <div className="form row">
        {(["requirement_id", "environment", "scope", "artefact_digest", "evidence", "owner"] as const).map((f) =>
          <label key={f}>{t(`response.field.${f}`)}<input value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} /></label>)}
        <label>{t("response.field.outcome")}<select value={form.outcome} onChange={(e) => setForm({ ...form, outcome: e.target.value })}>
          {["PASS", "FAIL", "BLOCKED", "NOT RUN", "N/A"].map((o) => <option key={o}>{o}</option>)}</select></label>
        <label>{t("response.field.coverage")}<select value={form.coverage} onChange={(e) => setForm({ ...form, coverage: e.target.value })}>
          {["observe", "respond", "drill"].map((o) => <option key={o} value={o}>{t(`response.cov.${o}`)}</option>)}</select></label>
        <Act className="primary" label={t("response.record")} run={() => api("/v1/harness/assertions", { body: form })} onDone={reload} />
      </div>
      {assertions.data?.length === 0 && <Empty>{t("response.noAssertions")}</Empty>}
      {(assertions.data?.length ?? 0) > 0 && <table><thead><tr><th>{t("response.field.requirement_id")}</th>
        <th>{t("response.field.environment")}</th><th>{t("response.field.scope")}</th><th>{t("response.field.outcome")}</th>
        <th>{t("response.field.coverage")}</th><th>{t("response.field.artefact_digest")}</th><th>{t("response.field.evidence")}</th>
        <th>{t("response.field.owner")}</th><th>{t("response.observedAt")}</th></tr></thead>
        <tbody>{assertions.data!.map((x) => <tr key={x.id}><td>{x.requirement_id}</td><td>{x.environment}</td><td>{x.scope}</td>
          <td>{x.outcome}</td><td>{t(`response.cov.${x.coverage}`)}</td><td><code>{x.artefact_digest}</code></td><td>{x.evidence}</td>
          <td>{x.owner}</td><td>{formatDateTime(x.observed_at, locale)}</td></tr>)}</tbody></table>}
    </Shell>);
}
