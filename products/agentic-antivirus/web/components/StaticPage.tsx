"use client";
import { useI18n } from "../lib/i18n";
import Link from "next/link";
import type { ReactNode } from "react";

export function StaticPage({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <main id="main" className="main" style={{ maxWidth: "46rem", margin: "2rem auto" }}>
      <p><Link href="/">{t("app.name")}</Link></p>
      <h1>{title}</h1>
      {children}
    </main>);
}
