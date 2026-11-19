"use client";
import { Shell } from "../../components/Shell";
import { Status, useApi } from "../../components/ui";
import { DecisionCard, type ActionRequest } from "../../components/Decision";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

export default function Approvals() {
  const { t } = useI18n();
  const { locale } = useI18n();
  const all = useApi<ActionRequest[]>("/v1/actions");
  const dev = useApi<any[]>("/v1/devices");
  const tenants = useApi<any[]>("/v1/tenants");
  const names = Object.fromEntries([...(dev.data ?? []).map((d) => [d.id, d.hostname]),
    ...(tenants.data ?? []).map((x) => [x.tenant_id, x.tenant_name])]);
  const open = (all.data ?? []).filter((a) => a.status === "proposed" || a.status === "approved");
  const done = (all.data ?? []).filter((a) => !(a.status === "proposed" || a.status === "approved"));
  return (
    <Shell pending={open.length}>
      <h1>{t("nav.actions")}</h1>
      <p className="lede">{t("ui.every_action_that_changes_a_device")}</p>
      <Status error={all.error} loading={!all.data} />
      <section className="decisions">{open.map((a) => <DecisionCard key={a.id} a={a} names={names} onChange={all.reload} />)}</section>
      {open.length === 0 && all.data && <p>{t("ui.no_actions_are_waiting")}</p>}
      <h2>{t("ui.history")}</h2>
      <table><thead><tr><th>{t("ui.action")}</th><th>{t("ui.targets")}</th><th>{t("ui.status")}</th><th>{t("ui.requested_by")}</th><th>{t("ui.when")}</th></tr></thead>
        <tbody>{done.map((a) => <tr key={a.id}><td>{a.action_type}</td><td>{a.targets.map((x) => names[x] ?? x).join(", ")}</td>
          <td>{a.status}{a.policy_decision.reason ? `: ${a.policy_decision.reason}` : ""}</td>
          <td>{a.proposed_by.startsWith("ai:") ? "AI assistant" : a.proposed_by.startsWith("user:") ? "a person" : a.proposed_by}</td>
          <td>{formatDateTime(a.created_at, locale)}</td></tr>)}</tbody></table>
    </Shell>);
}
