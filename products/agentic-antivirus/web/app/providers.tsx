"use client";
import { useEffect, type ReactNode } from "react";
import { I18nProvider } from "../lib/i18n";

export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => { /* PWA install optional */ });
    }
  }, []);
  return <I18nProvider>{children}</I18nProvider>;
}
