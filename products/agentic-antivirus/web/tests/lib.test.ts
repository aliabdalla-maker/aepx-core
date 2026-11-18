import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { formatMessage, localeIncludes, formatCurrency } from "../lib/format";
import { AdPacer, shouldRenderAd, readConsent, NEVER, type AdsConfig } from "../lib/ads";
import { LOCALES, RTL, resolve } from "../lib/i18n";
import { voicesFor } from "../lib/voice";

describe("ICU formatting (L10N-05/06)", () => {
  const tpl = "{count, plural, one {# device} other {# devices}}";
  it("uses each locale's plural rules", () => {
    expect(formatMessage(tpl, "en", { count: 1 })).toBe("1 device");
    expect(formatMessage(tpl, "en", { count: 1234 })).toBe("1,234 devices");
    expect(formatMessage(tpl, "de", { count: 1234 })).toBe("1.234 devices");
    expect(formatMessage("{n, plural, =0 {none} other {#}}", "en", { n: 0 })).toBe("none");
    expect(new Intl.PluralRules("ar").select(3)).toBe("few");
  });
  it("interpolates and formats currency", () => {
    expect(formatMessage("Updated {time}", "en", { time: "now" })).toBe("Updated now");
    expect(formatCurrency(4.99, "GBP", "en-GB")).toBe("£4.99");
  });
  it("searches accent- and case-insensitively (L10N-09)", () => {
    expect(localeIncludes("Café Réception", "cafe recep", "fr")).toBe(true);
    expect(localeIncludes("finance-lt", "xyz", "en")).toBe(false);
  });
});

describe("locale catalogue (L10N-01/07/08)", () => {
  it("matches the server catalogue exactly", () => {
    const py = readFileSync(new URL("../../control-plane/app/i18n.py", import.meta.url), "utf8");
    const server = [...py.slice(py.indexOf("LOCALES = ["), py.indexOf("]", py.indexOf("LOCALES = ["))).matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect([...LOCALES]).toEqual(server);
    expect(LOCALES.length).toBe(100);
    expect([...RTL].sort()).toEqual(["ar", "fa", "he", "ps", "ur", "yi"]);
  });
  it("falls back to English for missing keys", () => {
    expect(resolve({}, "nav.devices")).toBe("Devices");
    expect(resolve({ "nav.devices": "Geräte" }, "nav.devices")).toBe("Geräte");
    expect(resolve(null, "missing.key")).toBe("missing.key");
  });
});

describe("ads (owner requirement: 100% trial, 95% fewer when paid)", () => {
  const cfg: AdsConfig = { adsense: { client: "ca-pub-2980680946304710", enabled: true, slots: [] },
    placements: { allowed: ["dashboard_banner"], never: [...NEVER] } };
  it("paces exactly", () => {
    const full = new AdPacer(1), paid = new AdPacer(0.05);
    let a = 0, b = 0;
    for (let i = 0; i < 1000; i++) { a += +full.next(); b += +paid.next(); }
    expect([a, b]).toEqual([1000, 50]);
  });
  it("needs env flag, consent, valid web slot and an allowed placement", () => {
    const base = { cfg, placement: "dashboard_banner", consent: "granted" as const, envEnabled: true, slot: "1234567890" };
    expect(shouldRenderAd(base)).toBe(true);
    expect(shouldRenderAd({ ...base, envEnabled: false })).toBe(false);
    expect(shouldRenderAd({ ...base, consent: "unknown" })).toBe(false);
    expect(shouldRenderAd({ ...base, slot: "ca-app-pub-2980680946304710/1032845563" })).toBe(false);
    expect(shouldRenderAd({ ...base, placement: "approval_screens" })).toBe(false);
  });
  it("reads consent defensively", () => {
    expect(readConsent({ getItem: () => { throw new Error("blocked"); } })).toBe("unknown");
    expect(readConsent({ getItem: () => "granted" })).toBe("granted");
  });
});

describe("voice capability detection (VOC-03)", () => {
  const all = [{ name: "A", lang: "en-GB", localService: true, voiceURI: "a" }, { name: "B", lang: "fil-PH", localService: false, voiceURI: "b" },
    { name: "C", lang: "nb-NO", localService: true, voiceURI: "c" }, { name: "D", lang: "zh-CN", localService: true, voiceURI: "d" }];
  it("maps catalogue codes to device voices", () => {
    expect(voicesFor("en", all).map((v) => v.name)).toEqual(["A"]);
    expect(voicesFor("tl", all).map((v) => v.name)).toEqual(["B"]);
    expect(voicesFor("no", all).map((v) => v.name)).toEqual(["C"]);
    expect(voicesFor("zh-Hans", all).map((v) => v.name)).toEqual(["D"]);
    expect(voicesFor("sat", all)).toEqual([]);
  });
});
