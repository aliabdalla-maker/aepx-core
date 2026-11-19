// AdSense (web) gating for the Agentic Antivirus console. Ads render only when all hold:
//  1. NEXT_PUBLIC_ADS_ENABLED === "true" and the server's ads config has adsense.enabled
//  2. a valid AdSense client (ca-pub-<16 digits>) and a 10-digit web slot for the placement
//     (AdMob "ca-app-pub-..." unit IDs cannot serve on the web and are rejected)
//  3. the visitor granted consent
//  4. the placement is allowed (never approval/containment/warning/quarantine/login/payment/audit)
//  5. pacing at the server-issued ad rate: 1.0 trial/unpaid, 0.05 after paying £4.99 (95% fewer)
export const PUBLISHER_ID = "pub-2980680946304710";
export const CONSENT_KEY = "aav.adConsent";
export type Consent = "granted" | "denied" | "unknown";
export type Placement = "dashboard_banner" | "device_list_banner" | "incident_list_banner" | "settings_banner" | "help_banner";
export const NEVER = ["approval_screens", "containment_screens", "threat_warning_dialogs", "quarantine_review", "login",
  "payment_screens", "audit_views"] as const;

const CLIENT_RE = /^ca-pub-\d{16}$/;
const SLOT_RE = /^\d{10}$/;

export type AdsConfig = { adsense: { client: string; enabled: boolean; slots: { placement: string; slot: string }[] };
  placements: { allowed: string[]; never: string[] } };

export function slotFor(cfg: AdsConfig, placement: string, env: Record<string, string | undefined>): string | undefined {
  const fromEnv = env[`NEXT_PUBLIC_ADSENSE_SLOT_${placement.toUpperCase()}`];
  return fromEnv ?? cfg.adsense.slots.find((s) => s.placement === placement)?.slot;
}

export function shouldRenderAd(args: { cfg: AdsConfig; placement: string; consent: Consent; envEnabled: boolean;
  slot: string | undefined }): boolean {
  const { cfg, placement, consent, envEnabled, slot } = args;
  if (!envEnabled || !cfg.adsense.enabled || consent !== "granted") return false;
  if (!cfg.placements.allowed.includes(placement) || cfg.placements.never.includes(placement)) return false;
  return CLIENT_RE.test(cfg.adsense.client) && typeof slot === "string" && SLOT_RE.test(slot);
}

// Same pacing as the control plane's AdGate: show when floor(n*rate) increases.
export class AdPacer {
  private n = 0;
  constructor(public rate: number) {
    if (!(rate >= 0 && rate <= 1)) throw new Error("rate must be in [0,1]");
  }
  next(): boolean {
    const before = Math.floor(this.n * this.rate);
    this.n += 1;
    return Math.floor(this.n * this.rate) > before;
  }
}

export function readConsent(storage: Pick<Storage, "getItem"> | undefined): Consent {
  try {
    const v = storage?.getItem(CONSENT_KEY);
    return v === "granted" || v === "denied" ? v : "unknown";
  } catch {
    return "unknown";
  }
}
