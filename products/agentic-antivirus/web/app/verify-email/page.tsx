"use client";
import Link from "next/link";
import { useEffect } from "react";
import { api } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { AuthPage, tokenParam, useSubmit } from "../../components/AuthForm";

export default function Verify() {
  const { t } = useI18n();
  const s = useSubmit();
  useEffect(() => { s.run(async () => { await api("/v1/auth/verify-email", { body: { token: tokenParam() } }); return t("auth.verified"); }); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []);
  return <AuthPage title="Verify email">{s.view}<Link href="/login">{t("auth.login")}</Link></AuthPage>;
}
