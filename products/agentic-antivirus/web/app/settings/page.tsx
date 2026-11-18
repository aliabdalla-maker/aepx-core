"use client";
import { useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, AdSlot, Status, useApi } from "../../components/ui";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";

export default function Settings() {
  const { t } = useI18n();
  const schema = useApi<Record<string, Record<string, { type: string; sensitive: boolean; enum: string[] | null }>>>("/v1/settings/schema");
  const vals = useApi<any[]>("/v1/settings");
  const locs = useApi<any[]>("/v1/i18n/locales");
  const members = useApi<any[]>("/v1/members");
  const lic = useApi("/v1/licence");
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [inviteEmail, setInviteEmail] = useState("");
  const [role, setRole] = useState("security_analyst");
  const current = (c: string, k: string) => vals.data?.find((v) => v.category === c && v.key === k)?.value;
  const parse = (type: string, raw: string) => type === "bool" ? raw === "true" : type === "int" ? parseInt(raw, 10)
    : type === "float" ? parseFloat(raw) : type === "list" ? raw.split(",").map((s) => s.trim()).filter(Boolean) : raw;
  return (
    <Shell>
      <h1>{t("nav.settings")}</h1>
      <Status error={schema.error} loading={!schema.data} />
      {schema.data && Object.entries(schema.data).map(([cat, keys]) => (
        <section key={cat}><h2>{cat.replace(/_/g, " ")}</h2>
          <table><tbody>{Object.entries(keys).map(([k, spec]) => {
            const id = `${cat}.${k}`, v = current(cat, k);
            return <tr key={id}><th scope="row">{k.replace(/_/g, " ")}{spec.sensitive && <span className="chip">administrator</span>}</th>
              <td>{v === undefined ? <span className="hint">not set</span> : <code>{JSON.stringify(v)}</code>}</td>
              <td className="row">
                {spec.enum ? <select aria-label={id} value={edit[id] ?? ""} onChange={(e) => setEdit({ ...edit, [id]: e.target.value })}>
                  <option value="">choose</option>{spec.enum.map((o) => <option key={o}>{o}</option>)}</select>
                  : spec.type === "bool" ? <select aria-label={id} value={edit[id] ?? ""} onChange={(e) => setEdit({ ...edit, [id]: e.target.value })}>
                    <option value="">choose</option><option value="true">on</option><option value="false">off</option></select>
                  : <input aria-label={id} value={edit[id] ?? ""} onChange={(e) => setEdit({ ...edit, [id]: e.target.value })} />}
                <Act label={t("common.save")} run={() => api(`/v1/settings/${cat}/${k}`, { method: "PUT", body: { value: parse(spec.type, edit[id] ?? "") } })} onDone={vals.reload} />
                <Act label="Undo last change" run={async () => {
                  const h = await api<any[]>(`/v1/settings/${cat}/${k}/history`);
                  if (h.length < 2) throw new Error("No earlier version");
                  await api(`/v1/settings/${cat}/${k}/rollback/${h[1].version}`, { method: "POST" }); }} onDone={vals.reload} />
              </td></tr>; })}</tbody></table></section>))}

      <h2>People</h2>
      <table><thead><tr><th>User</th><th>Role</th></tr></thead>
        <tbody>{(members.data ?? []).map((m) => <tr key={m.user_id + m.role}><td><code>{m.user_id}</code></td><td>{m.role}</td></tr>)}</tbody></table>
      <div className="row"><label style={{ margin: 0 }}>Email<input type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} /></label>
        <label style={{ margin: 0 }}>Role<select value={role} onChange={(e) => setRole(e.target.value)}>
          {["tenant_admin", "it_admin", "security_analyst", "endpoint_user", "auditor", "msp_operator"].map((r) => <option key={r}>{r}</option>)}</select></label>
        <Act label="Send invitation" run={() => api("/v1/auth/invitations", { body: { email: inviteEmail, role } })} onDone={members.reload} /></div>

      <h2>{t("settings.locale_coverage")}</h2>
      <p className="lede">Languages without a complete translation fall back to English. Coverage is measured, not estimated.</p>
      <table><thead><tr><th>Language</th><th>Direction</th><th>Translated</th><th>Status</th></tr></thead>
        <tbody>{(locs.data ?? []).map((l) => <tr key={l.locale}><td>{l.locale}</td><td>{l.direction}</td>
          <td>{l.keys_translated}/{l.keys_total} ({l.coverage_pct}%)</td><td>{l.status}</td></tr>)}</tbody></table>
      {lic.data && <AdSlot placement="settings_banner" rate={lic.data.ad_rate} />}
    </Shell>);
}
