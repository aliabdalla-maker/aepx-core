"use client";
import { useCallback, useEffect, useState } from "react";
import type { AuditEvent, IdeApi, Member } from "../lib/api";
import { MEMBER_ROLES } from "../lib/api";
import { ago } from "../lib/modules";

// Keycloak account console for the IDE realm: users add an authenticator app (TOTP) here; the
// sign-in flow then asks for the code on every login.
const ACCOUNT_SECURITY = (process.env.NEXT_PUBLIC_OIDC_AUTHORITY || "https://auth.softwareequality.com/realms/aepx")
  .replace(/\/$/, "") + "/account/#/security/signingin";

type Props = { api: IdeApi | null; role?: string; onStatus: (m: string) => void };
const ROLE_HELP: Record<string, string> = {
  owner: "Everything, including owners", admin: "Everything except changing owners",
  editor: "Developer: build, edit, run agents", media_editor: "Media files only (audio/, music/, film/ …)",
  reviewer: "Read and approve agent plans", viewer: "Read only",
};

/** Members and roles (spec §5) plus the tamper-evident audit trail. */
export default function TeamPanel({ api, role, onStatus }: Props) {
  const [members, setMembers] = useState<Member[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [integrity, setIntegrity] = useState<string>("");
  const [invite, setInvite] = useState({ subject: "", role: "editor" });
  const manage = role === "owner" || role === "admin";
  const audits = manage || role === "reviewer";
  const fail = useCallback((e: unknown) => onStatus(String((e as Error).message ?? e)), [onStatus]);

  const load = useCallback(() => {
    if (!api) return;
    api.members().then(setMembers).catch(fail);
    if (audits) api.auditEvents(50).then(setEvents).catch(fail);
  }, [api, audits, fail]);
  useEffect(load, [load]);

  async function change(subject: string, next: string) {
    if (!api) return;
    if (next === "remove" && !window.confirm(`Remove ${subject} from this workspace?`)) return;
    try { await api.setMember(subject, next); onStatus(`${subject}: ${next}`); load(); } catch (e) { fail(e); }
  }

  async function verify() {
    if (!api) return;
    try {
      const r = await api.verifyAudit();
      setIntegrity(r.intact ? "Audit chain intact ✓" : `Tampering detected at event ${r.first_broken_event}`);
    } catch (e) { fail(e); }
  }

  if (!api) return <p className="muted">Sign in to manage your team.</p>;
  return <div className="team">
    <p className="muted small">Your role: <strong>{role ?? "…"}</strong>{role && ROLE_HELP[role] ? ` — ${ROLE_HELP[role]}` : ""}</p>
    <p className="small"><a href={ACCOUNT_SECURITY} target="_blank" rel="noopener noreferrer">Set up two-step sign-in (authenticator app)</a>
      <span className="muted"> — recommended for owners and admins.</span></p>
    <h4>Members</h4>
    <ul className="members">{members.map(m => <li key={m.subject} className="row">
      <span className="member-id" title={m.subject}>{m.subject}</span><span className="spacer" />
      {manage ? <select aria-label={`Role for ${m.subject}`} value={m.role} onChange={e => void change(m.subject, e.target.value)}>
        {MEMBER_ROLES.map(r => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
        <option value="remove">remove…</option>
      </select> : <span className="badge">{m.role.replace("_", " ")}</span>}
    </li>)}</ul>
    {manage && <div className="row wrap">
      <input aria-label="Member user id" placeholder="User id (subject)" maxLength={255} value={invite.subject}
        onChange={e => setInvite(i => ({ ...i, subject: e.target.value }))} />
      <select aria-label="New member role" value={invite.role} onChange={e => setInvite(i => ({ ...i, role: e.target.value }))}>
        {MEMBER_ROLES.map(r => <option key={r} value={r} title={ROLE_HELP[r]}>{r.replace("_", " ")}</option>)}
      </select>
      <button disabled={!invite.subject.trim()} onClick={() => { void change(invite.subject.trim(), invite.role); setInvite(i => ({ ...i, subject: "" })); }}>Add</button>
    </div>}
    {audits && <>
      <div className="row"><h4>Audit trail</h4><span className="spacer" /><button className="small" onClick={() => void verify()}>Verify integrity</button></div>
      {integrity && <p className="small" role="status">{integrity}</p>}
      <ol className="audit">{events.map(e => <li key={e.id}>
        <code>{e.action}</code> <span className="muted small">{e.resource_type} · {ago(e.created_at)} · {e.actor.slice(0, 18)}</span>
      </li>)}</ol>
    </>}
  </div>;
}
