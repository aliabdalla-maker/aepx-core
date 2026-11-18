"use client";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { describeError } from "../lib/api";
import { useI18n } from "../lib/i18n";

export function AuthPage({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <main id="main" className="main" style={{ maxWidth: "32rem", margin: "4rem auto" }}>
      <p className="brand"><img src={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/icons/icon.svg`} alt="" width={32} height={32} /> {t("app.name")}</p>
      <h1>{title}</h1>
      {children}
      <p className="lede" style={{ marginTop: "2rem" }}><Link href="/help">{t("nav.help")}</Link>{" "}<Link href="/privacy">{t("nav.privacy")}</Link></p>
    </main>);
}

export function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const run = async (f: () => Promise<string | void>) => {
    setBusy(true); setErr(null); setOk(null);
    try { const m = await f(); if (m) setOk(m); } catch (e) { setErr(describeError(e)); } finally { setBusy(false); }
  };
  const view = <>{err && <p className="error" role="alert">{err}</p>}{ok && <p className="banner" role="status">{ok}</p>}</>;
  return { busy, run, view };
}

export function tokenParam(): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("token") ?? "";
}
