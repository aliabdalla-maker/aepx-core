"use client";
import { Shell } from "../../components/Shell";
import { Status, useApi } from "../../components/ui";
import { DecisionCard, type ActionRequest } from "../../components/Decision";
import { useI18n } from "../../lib/i18n";
import { formatDateTime } from "../../lib/format";

export default function Approvals() {
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
      <h1>Approvals</h1>
      <p className="lede">Every action that changes a device, an account or traffic passes the policy engine and AEP-X governance. An approval covers one action, its exact targets, this organisation, and a fixed time.</p>
      <Status error={all.error} loading={!all.data} />
      <section className="decisions">{open.map((a) => <DecisionCard key={a.id} a={a} names={names} onChange={all.reload} />)}</section>
      {open.length === 0 && all.data && <p>No actions are waiting.</p>}
      <h2>History</h2>
      <table><thead><tr><th>Action</th><th>Targets</th><th>Status</th><th>Requested by</th><th>When</th></tr></thead>
        <tbody>{done.map((a) => <tr key={a.id}><td>{a.action_type}</td><td>{a.targets.map((x) => names[x] ?? x).join(", ")}</td>
          <td>{a.status}{a.policy_decision.reason ? `: ${a.policy_decision.reason}` : ""}</td>
          <td>{a.proposed_by.startsWith("ai:") ? "AI assistant" : a.proposed_by.startsWith("user:") ? "a person" : a.proposed_by}</td>
          <td>{formatDateTime(a.created_at, locale)}</td></tr>)}</tbody></table>
    </Shell>);
}
