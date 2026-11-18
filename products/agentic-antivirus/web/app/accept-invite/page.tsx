"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, session } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { AuthPage, tokenParam, useSubmit } from "../../components/AuthForm";

export default function Accept() {
  const { t } = useI18n();
  const router = useRouter();
  const [pw, setPw] = useState("");
  const [name, setName] = useState("");
  const s = useSubmit();
  return (
    <AuthPage title="Join your organisation">
      <form className="form" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
        const r = await api("/v1/auth/invitations/accept", { body: { token: tokenParam(), password: pw, display_name: name } });
        session.set(r.access_token);
        router.replace("/");
      }); }}>
        <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>{t("auth.password")} <span className="hint">{t("auth.password_rules")}</span>
          <input type="password" minLength={12} required value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" /></label>
        {s.view}<button className="primary" disabled={s.busy}>Join</button>
      </form>
    </AuthPage>);
}
