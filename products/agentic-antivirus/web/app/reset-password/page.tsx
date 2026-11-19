"use client";
import Link from "next/link";
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
        return t("auth.passwordChanged");
      }); }}>
        <label>{t("auth.new_password")} <span className="hint">{t("auth.password_rules")}</span>
          <input type="password" minLength={12} required value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" /></label>
        {s.view}<div className="row"><button className="primary" disabled={s.busy}>{t("auth.reset")}</button><Link href="/login">{t("auth.login")}</Link></div>
      </form>
    </AuthPage>);
}
