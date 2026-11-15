// Web AdSense gating. Ads are OFF unless every condition holds:
//  1. NEXT_PUBLIC_ADS_ENABLED === "true"
//  2. a well-formed AdSense client (ca-pub-<16 digits>) and a 10-digit web slot ID
//     (AdMob "ca-app-pub-..." unit IDs are rejected: they cannot serve on the web)
//  3. the visitor explicitly granted consent
//  4. the surface is not an editing / approval / terminal surface (accidental-click policy)

export type AdSurface = "sidebar" | "projectHome" | "editor" | "approvals" | "terminal";
export type Consent = "granted" | "denied" | "unknown";

export const SAFE_AD_SURFACES: readonly AdSurface[] = ["sidebar", "projectHome"];
export const CONSENT_KEY = "aepx.adConsent";
export const PUBLISHER_ID = "pub-2980680946304710";

const CLIENT_RE = /^ca-pub-\d{16}$/;
const SLOT_RE = /^\d{10}$/;

export type AdsenseSettings = {
  enabled: boolean;
  client: string;
  slots: Partial<Record<AdSurface, string>>;
};

type Env = Record<string, string | undefined>;

export function adsenseSettings(env: Env): AdsenseSettings {
  const client = env.NEXT_PUBLIC_ADSENSE_CLIENT ?? `ca-${PUBLISHER_ID}`;
  const slots: Partial<Record<AdSurface, string>> = {};
  const sidebar = env.NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR;
  const home = env.NEXT_PUBLIC_ADSENSE_SLOT_PROJECT_HOME;
  if (sidebar) slots.sidebar = sidebar;
  if (home) slots.projectHome = home;
  return { enabled: env.NEXT_PUBLIC_ADS_ENABLED === "true", client, slots };
}

export function isValidClient(client: string) { return CLIENT_RE.test(client); }
export function isValidWebSlot(slot: string | undefined): slot is string {
  return typeof slot === "string" && SLOT_RE.test(slot);
}

export function shouldRenderAd(settings: AdsenseSettings, surface: AdSurface, consent: Consent): boolean {
  if (!settings.enabled || consent !== "granted") return false;
  if (!SAFE_AD_SURFACES.includes(surface)) return false;
  return isValidClient(settings.client) && isValidWebSlot(settings.slots[surface]);
}

/**
 * Server-issued ad rate: 1.0 on trial/free, 0.05 for £4.99 subscribers ("95% ads off").
 * Deterministic thinning: with rate r, show the 1st, (1/r+1)th, ... opportunity (1 in 20 at 5%).
 */
export function impressionAllowed(rate: number, opportunity: number): boolean {
  if (!Number.isFinite(rate) || rate <= 0) return false;
  if (rate >= 1) return true;
  const every = Math.max(1, Math.round(1 / rate));
  return Number.isInteger(opportunity) && opportunity >= 0 && opportunity % every === 0;
}

/** Read consent defensively: storage can be unavailable (privacy mode, embedded contexts). */
export function readConsent(storage: Pick<Storage, "getItem"> | undefined): Consent {
  try {
    const value = storage?.getItem(CONSENT_KEY);
    return value === "granted" || value === "denied" ? value : "unknown";
  } catch { return "unknown"; }
}

export function writeConsent(storage: Pick<Storage, "setItem"> | undefined, consent: "granted" | "denied") {
  try { storage?.setItem(CONSENT_KEY, consent); } catch { /* ignore: consent stays unknown, so no ads */ }
}
