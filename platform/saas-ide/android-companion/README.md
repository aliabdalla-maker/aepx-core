# AEP-X Android companion (AdMob)

A native Kotlin/Jetpack Compose companion to the web IDE: sign in with your organisation's OIDC provider,
browse projects and agent runs, read plans and audit trails, and approve or reject plans and MCP tool calls.
It is the only AEP-X surface that can serve **AdMob** ads (AdMob does not serve on websites or inside a
Trusted Web Activity).

## Ads: how the six units are wired

`../monetization/ads-config.json` is the single source of truth. The build copies it into the APK
(`copyAdsConfig` task); the web IDE's tests read the same file.

| AdMob item | Value |
|---|---|
| App ID (release manifest) | `ca-app-pub-2980680946304710~2617421798` |
| Units | `…/1032845563`, `…/2172884450`, `…/3668921616`, `…/5953999752`, `…/6184281650`, `…/6514576804` |

Each unit has `format` and `placement`, both `null` today, so **no unit is ever requested**. To turn a unit on:

1. In the AdMob console, read the unit's format (banner, interstitial, rewarded, rewarded interstitial, native, app open).
2. Set `format` to that value and `placement` to one of:

   | placement | format | where |
   |---|---|---|
   | `project_list_banner` | banner | bottom of the projects list |
   | `runs_list_banner` | banner | bottom of a project's runs list |
   | `native_feed` | native | end of the projects list, labelled "Ad" |
   | `run_completed_interstitial` | interstitial | when leaving a finished run (max 3/session, ≥3 min apart) |
   | `app_open` | app_open | once per 4 h after consent |

   Rewarded formats are accepted in the config but have no placement until there is a product reason to reward users.
3. Debug builds then show Google **test** ads for that placement. Set `admob.enabled: true` only for a release you intend to ship.

Hard rules enforced in code (`ads/AdPolicy.kt`, unit-tested):
- A unit is requested only when its declared format matches the placement; mismatches, unknown values,
  duplicate units/placements, or another publisher's IDs make the whole config invalid → no ads.
- Debug builds use Google's sample app ID and sample units; the CI job fails if the live ID leaks into debug.
- `MobileAds` initialises only after Google UMP consent (`canRequestAds()`) and only if a placement can serve.
  UK/EEA users get the consent form; "Privacy options" is on the About screen when required.
- Run-detail/approval screens never show ads.

## Configure and build

```bash
# deployment identifiers (not secrets) — or put them in ~/.gradle/gradle.properties
gradle -Paepx.apiBaseUrl=https://ide-api.example.com -Paepx.tenant=acme \
       -Paepx.oidcIssuer=https://login.example.com -Paepx.oidcClientId=aepx-android \
       testDebugUnitTest assembleDebug
```

- Register redirect URI `com.equalitysoftware.aepx.companion:/oauth2redirect` (public client, PKCE) with your IdP.
- Release builds require HTTPS for the API; debug may use `http://10.0.2.2` (emulator only).
- Tokens are held in memory only. No keystore, signing config or Play Console upload is included; sign and
  upload through your normal release process (internal testing first).
- Gradle 8.10.x and JDK 17; CI: `.github/workflows/android-companion.yml`. Generate a wrapper locally with
  `gradle wrapper --gradle-version 8.10.2` if you want one.

## Before turning live ads on
AdMob app/package association, `app-ads.txt` on the developer website, Play Data safety form, privacy policy,
UMP consent message published in AdMob, and testing with registered test devices. Never click live ads yourself.
