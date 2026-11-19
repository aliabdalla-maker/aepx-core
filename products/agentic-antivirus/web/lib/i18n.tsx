"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en from "../../shared/i18n/en.json";
import { formatMessage } from "./format";

// The 100-locale catalogue (same list as the control plane's app/i18n.py).
export const LOCALES = ["en", "es", "zh-Hans", "hi", "ar", "fr", "pt", "ru", "bn", "id", "ur", "de", "ja", "sw", "mr",
  "te", "tr", "ta", "vi", "ko", "it", "th", "gu", "fa", "pl", "uk", "pa", "ml", "jv", "nl", "ro", "hu", "el", "cs", "sv",
  "fi", "he", "da", "no", "sk", "bg", "sr", "hr", "lt", "lv", "et", "sl", "ca", "eu", "gl", "af", "am", "az", "be", "bs",
  "cy", "eo", "fil", "ha", "hy", "ig", "is", "ka", "kk", "km", "kn", "ku", "ky", "lo", "mk", "mn", "my", "ne", "or", "ps",
  "si", "sq", "su", "tg", "tk", "tl", "uz", "yo", "zu", "xh", "so", "rw", "mg", "ny", "sn", "st", "tn", "ts", "wo", "yi",
  "ceb", "hmn", "bho", "mai", "sat"] as const;
export const RTL = new Set(["ar", "fa", "he", "ps", "ur", "yi"]);
const KEY = "aav.locale";

type Messages = Record<string, string>;
type Ctx = { locale: string; dir: "ltr" | "rtl"; t: (k: string, v?: Record<string, unknown>) => string;
  setLocale: (l: string) => void; available: boolean; machine: number };

const I18nCtx = createContext<Ctx>({ locale: "en", dir: "ltr", t: (k) => (en as Messages)[k] ?? k,
  setLocale: () => {}, available: true, machine: 0 });

/** Number of machine-translated, not yet reviewed strings travels in this reserved key (L10N-11/12). */
export const MACHINE_KEY = "__machine_translated";

export function localeName(code: string, display: string): string {
  try {
    return new Intl.DisplayNames([display], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

export function resolve(messages: Messages | null, key: string): string {
  return messages?.[key] ?? (en as Messages)[key] ?? key;
}

export function I18nProvider({ children, fetchMessages }: { children: ReactNode;
  fetchMessages?: (l: string) => Promise<Messages> }) {
  const [locale, setLocaleState] = useState("en");
  const [messages, setMessages] = useState<Messages | null>(en as Messages);
  const [available, setAvailable] = useState(true);
  const [machine, setMachine] = useState(0);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(KEY);
      if (saved && (LOCALES as readonly string[]).includes(saved)) setLocaleState(saved);
      else {
        const nav = navigator.language;
        const match = LOCALES.find((l) => l === nav) ?? LOCALES.find((l) => l === nav.split("-")[0]);
        if (match) setLocaleState(match);
      }
    } catch { /* storage unavailable */ }
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (locale === "en") { setMessages(en as Messages); setAvailable(true); setMachine(0); return; }
    (fetchMessages ?? defaultFetch)(locale).then((m) => {
      if (cancelled) return;
      const { [MACHINE_KEY]: mt, ...own } = m;
      setMessages({ ...(en as Messages), ...own });
      setAvailable(Object.keys(own).length > 0);
      setMachine(Number(mt ?? 0));
    }).catch(() => { if (!cancelled) { setMessages(en as Messages); setAvailable(false); setMachine(0); } });
    return () => { cancelled = true; };
  }, [locale, fetchMessages]);

  const dir = RTL.has(locale) ? "rtl" : "ltr";
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = dir;
  }, [locale, dir]);

  const setLocale = useCallback((l: string) => {
    setLocaleState(l);
    try { window.localStorage.setItem(KEY, l); } catch { /* ignore */ }
  }, []);
  const t = useCallback((k: string, v?: Record<string, unknown>) => formatMessage(resolve(messages, k), locale, v),
    [messages, locale]);
  const value = useMemo(() => ({ locale, dir, t, setLocale, available, machine }),
    [locale, dir, t, setLocale, available, machine]) as Ctx;
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

async function defaultFetch(l: string): Promise<Messages> {
  const { api } = await import("./api");
  const r = await api<{ messages: Messages; machine_translated?: string[] }>(`/v1/i18n/messages/${encodeURIComponent(l)}`);
  const own: Messages = {};
  for (const [k, v] of Object.entries(r.messages)) if (v !== (en as Messages)[k]) own[k] = v;
  if (r.machine_translated?.length) own[MACHINE_KEY] = String(r.machine_translated.length);
  return own;
}

export const useI18n = () => useContext(I18nCtx);
