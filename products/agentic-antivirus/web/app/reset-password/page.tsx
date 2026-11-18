"use client";
import { useState } from "react";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { AuthPage, tokenParam, useSubmit } from "../../components/AuthForm";

export default function Reset() {
  const { t } = useI18n();
  const [pw, setPw] = useState("");
  const s = useSubmit();
  return (
    <AuthPage title={t("auth.reset")}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
        await api("/v1/auth/password-reset/confirm", { body: { token: tokenParam(), new_password: pw } });
        return "Password changed. Sign in with your new password.";
      }); }}>
        <label>{t("auth.new_password")} <span className="hint">{t("auth.password_rules")}</span>
          <input type="password" minLength={12} required value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" /></label>
        {s.view}<div className="row"><button className="primary" disabled={s.busy}>{t("auth.reset")}</button><a href="/login">{t("auth.login")}</a></div>
      </form>
    </AuthPage>);
}
