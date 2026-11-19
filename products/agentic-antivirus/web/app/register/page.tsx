"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { AuthPage, useSubmit } from "../../components/AuthForm";
import { GoogleSignIn } from "../../components/GoogleSignIn";

export default function Register() {
  const { t, locale } = useI18n();
  const [f, setF] = useState({ email: "", password: "", organisation: "", display_name: "" });
  const s = useSubmit();
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <AuthPage title={t("auth.register")}>
      <p className="lede">Your organisation gets a 30-day free trial. After that it costs £4.99 per month for each user or device.</p>
      <GoogleSignIn organisation={f.organisation} text="signup_with" />
      <form className="form" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
        await api("/v1/auth/register", { body: { ...f, locale } });
        return t("auth.verify_sent");
      }); }}>
        <label>{t("auth.organisation")}<input required value={f.organisation} onChange={set("organisation")} /></label>
        <label>Your name<input value={f.display_name} onChange={set("display_name")} autoComplete="name" /></label>
        <label>{t("auth.email")}<input type="email" required value={f.email} onChange={set("email")} autoComplete="email" /></label>
        <label>{t("auth.password")} <span className="hint">{t("auth.password_rules")}</span>
          <input type="password" minLength={12} required value={f.password} onChange={set("password")} autoComplete="new-password" /></label>
        {s.view}
        <div className="row"><button className="primary" disabled={s.busy}>{t("auth.register")}</button><Link href="/login">{t("auth.login")}</Link></div>
      </form>
    </AuthPage>);
}
