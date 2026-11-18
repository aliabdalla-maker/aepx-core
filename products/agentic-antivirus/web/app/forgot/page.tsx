"use client";
import { useState } from "react";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { AuthPage, useSubmit } from "../../components/AuthForm";

export default function Forgot() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const s = useSubmit();
  return (
    <AuthPage title={t("auth.reset")}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
        await api("/v1/auth/password-reset/request", { body: { email } });
        return "If an account uses that address, we have sent a reset link. It works for one hour.";
      }); }}>
        <label>{t("auth.email")}<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        {s.view}<button className="primary" disabled={s.busy}>Send reset link</button>
      </form>
    </AuthPage>);
}
