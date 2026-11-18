"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, session } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { AuthPage, useSubmit } from "../../components/AuthForm";

export default function Login() {
  const { t } = useI18n();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const s = useSubmit();
  return (
    <AuthPage title={t("auth.login")}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
        const r = await api<{ access_token: string }>("/v1/auth/login", { body: { email, password } });
        session.set(r.access_token);
        const me = await api("/v1/auth/me");
        if (me.tenants[0]) session.setTenant(me.tenants[0].tenant_id);
        router.replace("/");
      }); }}>
        <label>{t("auth.email")}<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label>{t("auth.password")}<input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {s.view}
        <div className="row"><button className="primary" disabled={s.busy}>{t("auth.login")}</button>
          <Link href="/forgot">{t("auth.forgot")}</Link><Link href="/register">{t("auth.register")}</Link></div>
      </form>
    </AuthPage>);
}
