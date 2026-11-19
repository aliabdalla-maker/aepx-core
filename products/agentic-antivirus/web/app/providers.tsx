"use client";
import { useEffect, type ReactNode } from "react";
import { I18nProvider } from "../lib/i18n";

export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
      navigator.serviceWorker.register(`${base}/sw.js`, { scope: `${base}/` }).catch(() => { /* PWA install optional */ });
    }
  }, []);
  return <I18nProvider>{children}</I18nProvider>;
}
