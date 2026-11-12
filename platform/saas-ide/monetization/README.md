# AdSense and AdMob integration — configuration phase

The supplied identifiers are recorded in `ads-config.json`. **Live ad serving is disabled.**

## Important distinction
- **AdSense** is for the browser-based SaaS IDE. Publisher: `pub-2980680946304710`; script client: `ca-pub-2980680946304710`. The provided `ca-app-pub-...` values are **AdMob**, not web AdSense slots. No web slot ID has been supplied.
- **AdMob** is for a future native Android IDE companion app, **not** a Next.js browser page. The `~` ID is an AdMob app ID, and six `/` IDs are mobile ad units. Their formats (banner, interstitial, rewarded, etc.) are unknown, so do not assume or interchange them.

## Website steps
1. Confirm the production IDE website is approved in AdSense and the publisher ID is linked to it.
2. Copy `ads.txt` to the actual website's **root** `/ads.txt` (not the API service or an arbitrary repo path); verify its public URL.
3. For Auto ads, enable only after consent/privacy configuration and website approval, using the AdSense client `ca-pub-2980680946304710`.
4. For manual placements, obtain **web AdSense ad slot IDs** from AdSense; none of the six mobile unit IDs can be used as web slots.
5. Keep ads away from editor controls, terminals, code execution results and accidental-click surfaces. Offer an ad-free paid tier if desired.

## Android steps
1. Confirm the Android package is registered against the supplied AdMob app ID.
2. Merge `AndroidManifest-admob-snippet.xml` into the Android app's `<application>` and add the current Google Mobile Ads SDK dependency.
3. Check the format of **each** of the six units in AdMob before mapping it to banner, rewarded, interstitial or native ad code.
4. During development use Google test ad IDs or registered test devices, never repeatedly request or click live ads.
5. Obtain required user consent and implement applicable privacy disclosures, EEA/UK consent handling, and child-directed treatment before requesting live ads.
6. Publish `app-ads.txt` at the verified developer website root if required by AdMob; this file is not automatically deployed by committing it here.

## Safety and deployment
- No ad SDK is initialised by these files, and no ads are requested.
- IDs are identifiers, not API secrets; never commit account passwords or service keys.
- OCI London remains the deployment target, but there is no verified instance or production rollout.
- Activate only after reviewing ad network policies, consent, site/app verification and integration tests.

References: https://support.google.com/adsense/answer/105516 and https://support.google.com/admob/answer/7356431
