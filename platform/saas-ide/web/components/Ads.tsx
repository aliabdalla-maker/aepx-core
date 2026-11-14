"use client";
import { useEffect, useRef } from "react";
import type { AdSurface, Consent } from "../lib/ads";
import { adsenseSettings, shouldRenderAd } from "../lib/ads";

// Next.js inlines NEXT_PUBLIC_* at build time, so read each key explicitly.
export const ADSENSE = adsenseSettings({
  NEXT_PUBLIC_ADS_ENABLED: process.env.NEXT_PUBLIC_ADS_ENABLED,
  NEXT_PUBLIC_ADSENSE_CLIENT: process.env.NEXT_PUBLIC_ADSENSE_CLIENT,
  NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR: process.env.NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR,
  NEXT_PUBLIC_ADSENSE_SLOT_PROJECT_HOME: process.env.NEXT_PUBLIC_ADSENSE_SLOT_PROJECT_HOME,
});

declare global { interface Window { adsbygoogle?: unknown[] } }

function loadScript(client: string) {
  if (document.querySelector("script[data-aepx-adsense]")) return;
  const s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.dataset.aepxAdsense = "1";
  s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(client);
  document.head.appendChild(s);
}

/** Renders nothing unless shouldRenderAd() passes; never placed on editor/approval surfaces. */
export function AdSlot({ surface, consent }: { surface: AdSurface; consent: Consent }) {
  const ref = useRef<HTMLModElement>(null);
  const allowed = shouldRenderAd(ADSENSE, surface, consent);
  useEffect(() => {
    if (!allowed || !ref.current || ref.current.dataset.adsbygoogleStatus) return;
    loadScript(ADSENSE.client);
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch { /* blocked by extension */ }
  }, [allowed]);
  if (!allowed) return null;
  return <aside className="ad" aria-label="Advertisement">
    <span className="muted small">Advertisement</span>
    <ins ref={ref} className="adsbygoogle" style={{ display: "block" }}
      data-ad-client={ADSENSE.client} data-ad-slot={ADSENSE.slots[surface]} data-ad-format="auto"
      data-full-width-responsive="true" />
  </aside>;
}

/** Shown only when ads are configured and the visitor has not chosen yet. */
export function ConsentBanner({ consent, onChoose }: { consent: Consent; onChoose: (c: "granted" | "denied") => void }) {
  if (!ADSENSE.enabled || consent !== "unknown") return null;
  return <div className="consent" role="dialog" aria-label="Advertising consent">
    <p>AEP-X shows ads outside the editor to support the free tier. Allow Google to use cookies for ads?
      The editor, agent approvals and your code are never shown alongside ads.</p>
    <div className="row">
      <button className="primary" onClick={() => onChoose("granted")}>Allow</button>
      <button onClick={() => onChoose("denied")}>No ads cookies</button>
    </div>
  </div>;
}
