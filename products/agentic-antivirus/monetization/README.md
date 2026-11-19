# Monetisation: trial, subscription and ads

The owner set these requirements on 18 Nov 2026:

- **Trial:** 30 days free, with AdMob in the apps and AdSense on the web, at a 100% ad rate.
- **Price:** £4.99 per month, per user or per device. Each tenant chooses which (`PUT /v1/licence/settings`).
- **After payment:** 95% fewer adverts (ad rate 0.05). Pacing is deterministic, at exactly 1 in 20 opportunities. It is implemented the same way on the server (`AdGate`), the web (`AdPacer`), Android (`AdPacer.kt`) and iOS (`AdPolicy.Pacer`).
- **After the trial without payment:** one of three tenant-chosen policies:
  - `paywall_console_keep_protection` (default)
  - `free_with_full_ads`
  - `lock_all`, which stops endpoint protection and needs explicit acknowledgement

**Never show ads** on approval, containment, threat-warning, quarantine-review, sign-in, payment or audit screens.

## Identifiers in `ads-config.json`

| Item | Value |
|---|---|
| Publisher | `pub-2980680946304710` (AdSense client `ca-pub-2980680946304710`) |
| AdMob app | `ca-app-pub-2980680946304710~3427805116`. Units `/6357220784`, `/7811958596`, `/3898578402`, `/8550325196`, `/2665387781` |
| AdMob app | `ca-app-pub-2980680946304710~2617421798`. Units `/1032845563`, `/2172884450`, `/3668921616`, `/5953999752`, `/6184281650`, `/6514576804`. Also used by the AEP-X IDE Android companion, which is left unchanged |

## Before turning ads on

All serving is off (`enabled: false`), and every unit has `format: null`, so nothing is requested. To enable:

1. In the AdMob console, confirm which app ID is linked to which store package and platform. Set `platform` and `store_package`.
2. Copy each unit's format (banner, interstitial, native or app open) and assign a placement from `placements.allowed`.
3. Publish a UMP consent message (UK/EEA). The apps show it before any ad request.
4. For the web, create AdSense ad units (10-digit slot IDs) and add them to `adsense.slots`. The AdMob unit IDs cannot serve on the web.
5. Test with Google's test IDs, which debug builds always use. Then set `enabled: true` per network.
