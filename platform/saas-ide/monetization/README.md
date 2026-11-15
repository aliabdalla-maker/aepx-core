# AdSense and AdMob integration

`ads-config.json` (schema v2) is the single source of truth for both ad networks. **All live ad serving is
disabled** (`adsense.enabled` and `admob.enabled` are `false`) until the steps below are done.

## Which network serves where
- **AdMob** (`ca-app-pub-…`): native Android companion app only — `../android-companion/`.
  App ID `ca-app-pub-2980680946304710~2617421798`; six units, each with `format`/`placement` = `null`
  until you copy the format from the AdMob console. Units without a format are never requested.
  Debug builds always use Google's test IDs. See `../android-companion/README.md`.
- **AdSense** (`ca-pub-2980680946304710`): web IDE, sidebar and project home only — never the editor,
  approvals, terminals or code output. Needs 10-digit **web** slot IDs created in AdSense
  (`NEXT_PUBLIC_ADSENSE_SLOT_*`), `NEXT_PUBLIC_ADS_ENABLED=true`, and the visitor's consent. AdMob unit IDs
  are rejected as web slots by `web/lib/ads.ts`.
- **ads.txt**: served by the web app at `/ads.txt` (`web/public/ads.txt`). For AdMob, publish the same line
  as `app-ads.txt` on the developer website listed in Google Play.

## Turning ads on (owner actions)
1. AdMob console: confirm the Android package is linked to the app ID and note each unit's format.
2. Edit `ads-config.json`: set each unit's `format` and a `placement`, run the Android and web tests.
3. AdMob: publish a UMP consent message (GDPR/UK) — the app shows it before any ad request.
4. AdSense: get site approval and web slot IDs; for UK/EEA traffic use a Google-certified CMP before
   enabling personalised ads (the built-in banner only gates on explicit consent).
5. Test with Google test IDs / registered test devices. Never click live ads.
6. Only then set `enabled: true` for the network you are shipping.

IDs here are identifiers, not secrets; never commit account passwords, keystores or service keys.
References: https://support.google.com/adsense/answer/105516 · https://support.google.com/admob/answer/7356431 ·
https://developers.google.com/admob/android/privacy
