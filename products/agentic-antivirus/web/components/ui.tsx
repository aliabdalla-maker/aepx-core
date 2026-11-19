"use client";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, describeError } from "../lib/api";
import { AdPacer, readConsent, shouldRenderAd, slotFor, type AdsConfig, type Consent, CONSENT_KEY, PUBLISHER_ID } from "../lib/ads";
import { useI18n } from "../lib/i18n";
import { formatDateTime } from "../lib/format";
import { outputDevices, speak, startDictation, sttSupported, ttsSupported, voicesFor, type VoiceInfo } from "../lib/voice";

export function useApi<T = any>(path: string | null, query?: Record<string, any>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState<string | null>(null);
  const q = JSON.stringify(query ?? {});
  const load = useCallback(() => {
    if (!path) return;
    setError(null);
    api<T>(path, { query: JSON.parse(q) }).then((d) => { setData(d); setAt(new Date().toISOString()); })
      .catch((e) => setError(describeError(e)));
  }, [path, q]);
  useEffect(load, [load]);
  return { data, error, reload: load, at };
}

export function Freshness({ at }: { at: string | null }) {
  const { t, locale } = useI18n();
  return at ? <p className="lede" aria-live="polite">{t("dash.freshness", { time: formatDateTime(at, locale) })}</p> : null;
}

export function Status({ error, loading }: { error: string | null; loading: boolean }) {
  const { t } = useI18n();
  if (error) return <p className="error" role="alert">{error}</p>;
  if (loading) return <p aria-busy="true">{t("common.loading")}</p>;
  return null;
}

export function Sev({ s }: { s: string }) {
  return <span className={`sev sev-${s}`}>{s}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="banner">{children}</p>;
}

export function Act({ label, run, className, onDone, confirm }: { label: string; run: () => Promise<unknown>;
  className?: string; onDone?: (r: unknown) => void; confirm?: string }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <span className="row">
      <button className={className} disabled={busy} onClick={async () => {
        if (confirm && !window.confirm(confirm)) return;
        setBusy(true); setMsg(null);
        try { const r = await run(); onDone?.(r); } catch (e) { setMsg(describeError(e)); } finally { setBusy(false); }
      }}>{label}</button>
      {msg && <span className="error" role="alert">{msg}</span>}
    </span>);
}

// ---------------------------------------------------------------- voice
export function ReadAloud({ text }: { text: string }) {
  const { t, locale } = useI18n();
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [voice, setVoice] = useState<string>("");
  const [rate, setRate] = useState(1);
  const [pitch, setPitch] = useState(1);
  const [state, setState] = useState<"idle" | "speaking" | "paused">("idle");
  const [devices, setDevices] = useState<{ supported: boolean; devices: MediaDeviceInfo[] }>({ supported: false, devices: [] });
  useEffect(() => {
    if (!ttsSupported()) return;
    const refresh = () => {
      const v = voicesFor(locale, window.speechSynthesis.getVoices());
      setVoices(v);
      setVoice((cur) => (v.some((x) => x.uri === cur) ? cur : v[0]?.uri ?? ""));
    };
    refresh();
    window.speechSynthesis.addEventListener?.("voiceschanged", refresh);
    outputDevices().then(setDevices);
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", refresh);
  }, [locale]);
  if (!ttsSupported()) return null;
  return (
    <div className="row" role="group" aria-label={t("voice.speak")}>
      {voices.length === 0 ? <span className="hint">{t("voice.unavailable")}</span> : <>
        <button onClick={() => { speak(text, { lang: locale, voiceUri: voice, rate, pitch, onEnd: () => setState("idle") }); setState("speaking"); }}>
          {t("voice.speak")}</button>
        {state === "speaking" && <button onClick={() => { window.speechSynthesis.pause(); setState("paused"); }}>{t("voice.pause")}</button>}
        {state === "paused" && <button onClick={() => { window.speechSynthesis.resume(); setState("speaking"); }}>{t("voice.resume")}</button>}
        {state !== "idle" && <button onClick={() => { window.speechSynthesis.cancel(); setState("idle"); }}>{t("voice.stop")}</button>}
        <label style={{ margin: 0 }}><span className="hint">{t("voice.voice")}</span>
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
            {voices.map((v) => <option key={v.uri} value={v.uri}>{v.name} ({v.lang})</option>)}</select></label>
        <label style={{ margin: 0 }}><span className="hint">{t("voice.speed")} {rate.toFixed(1)}</span>
          <input type="range" min={0.5} max={2} step={0.1} value={rate} onChange={(e) => setRate(Number(e.target.value))} /></label>
        <label style={{ margin: 0 }}><span className="hint">{t("voice.pitch")} {pitch.toFixed(1)}</span>
          <input type="range" min={0} max={2} step={0.1} value={pitch} onChange={(e) => setPitch(Number(e.target.value))} /></label>
        <span className="hint">{t("voice.output_device")}: {devices.supported && devices.devices.length
          ? "system default (browsers do not let speech use another device)" : "system default"}</span>
      </>}
    </div>);
}

export function Dictate({ onText }: { onText: (s: string) => void }) {
  const { t, locale } = useI18n();
  const [stop, setStop] = useState<(() => void) | null>(null);
  if (!sttSupported()) return null;
  return stop
    ? <button onClick={() => { stop(); setStop(null); }}>{t("voice.stop")}</button>
    : <button onClick={() => {
        if (!window.confirm(t("voice.mic_consent"))) return;
        const s = startDictation(locale, (txt, final) => { if (final) onText(txt); }, () => setStop(null));
        if (s) setStop(() => s);
      }}>{t("voice.dictate")}</button>;
}

// ---------------------------------------------------------------- ads (AdSense, web)
let pacer: AdPacer | null = null;
export function AdSlot({ placement, rate }: { placement: string; rate: number }) {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<AdsConfig | null>(null);
  const [consent, setConsent] = useState<Consent>("unknown");
  const show = useRef<boolean | null>(null);
  useEffect(() => {
    api<AdsConfig>("/v1/ads/config").then(setCfg).catch(() => setCfg(null));
    try { setConsent(readConsent(window.localStorage)); } catch { /* ignore */ }
  }, []);
  const inApp = typeof navigator !== "undefined" && /AgenticAntivirusApp\//.test(navigator.userAgent);
  const slot = useMemo(() => (cfg ? slotFor(cfg, placement, process.env as any) : undefined), [cfg, placement]);
  const ok = !inApp && cfg && shouldRenderAd({ cfg, placement, consent, envEnabled: process.env.NEXT_PUBLIC_ADS_ENABLED === "true", slot });
  if (ok && show.current === null) {
    if (!pacer || pacer.rate !== rate) pacer = new AdPacer(rate);
    show.current = pacer.next();
  }
  useEffect(() => {
    if (!ok || !show.current) return;
    if (!document.querySelector("script[data-aav-adsense]")) {
      const s = document.createElement("script");
      s.async = true; s.dataset.aavAdsense = "1"; s.crossOrigin = "anonymous";
      s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-${PUBLISHER_ID}`;
      document.head.appendChild(s);
    }
    try { ((window as any).adsbygoogle = (window as any).adsbygoogle || []).push({}); } catch { /* blocked */ }
  }, [ok]);
  if (!inApp && cfg && consent === "unknown" && cfg.adsense.enabled) {
    return (
      <div className="banner" role="region" aria-label="Advertising consent">
        <p>We show adverts from Google AdSense on some pages. Allow personalised adverts?</p>
        <div className="row">
          <button onClick={() => { try { window.localStorage.setItem(CONSENT_KEY, "granted"); } catch {} setConsent("granted"); }}>Allow</button>
          <button onClick={() => { try { window.localStorage.setItem(CONSENT_KEY, "denied"); } catch {} setConsent("denied"); }}>Decline</button>
        </div>
      </div>);
  }
  if (!ok || !show.current) return null;
  return (
    <aside className="ad" aria-label={t("ads.label")}>
      <small>{t("ads.label")}</small>
      <ins className="adsbygoogle" style={{ display: "block" }} data-ad-client={cfg!.adsense.client} data-ad-slot={slot}
        data-ad-format="auto" data-full-width-responsive="true" />
    </aside>);
}
