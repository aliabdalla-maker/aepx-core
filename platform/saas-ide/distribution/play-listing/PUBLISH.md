# Publishing AEP-X to Google Play: checklist

Google requires the **first** release of a new app to be created and uploaded by hand in Play Console. After that,
`.github/workflows/android-release.yml` can upload new versions (always as a draft on internal testing; you promote them).

## 1. Play Console app setup (once)
1. Play Console → **Create app**: name `AEP-X Agentic IDE`, default language English (United Kingdom), App, Free, accept the declarations.
2. **Store listing**: paste from `listing-en-GB.md`; upload `graphics/icon-512.png`, `graphics/feature-graphic-1024x500.png`
   and at least two phone screenshots.
3. **App content** (Policy → App content). Suggested answers for this app:
   - Privacy policy: `https://www.softwareequality.com/aepx/privacy.html`
   - Ads: **Yes, my app contains ads** (AdMob).
   - App access: **All or some functionality is restricted**. Provide a review account (username, password and tenant)
     so Google's reviewers can sign in.
   - Target audience: **18 and over** (professional tool).
   - Content rating questionnaire: category *Utility, Productivity, Communication, or Other*. Answer No to violence,
     sexuality, gambling and so on; user interaction: users cannot interact with each other in the app.
   - Data safety (see the table below).
   - Financial features: none. Government app: no. Health: no.
4. **Monetise → Subscriptions**: product ID `aepx_pro_monthly`, base plan *monthly, auto-renewing*, price **£4.99**
   (let Play convert other countries). Do **not** add a free-trial offer, because the 30-day trial is granted by the AEP-X server.
5. **Setup → API access**: link a Google Cloud project, create a service account with *Release manager* (for CI uploads)
   and *View financial data / Manage orders and subscriptions* (for the server's purchase verification).

## Data safety answers (match the privacy policy)
| Data type | Collected | Shared | Purpose | Notes |
| --- | --- | --- | --- | --- |
| User IDs (account identifier) | Yes | No | App functionality, account management | Required |
| Purchase history | Yes | No | App functionality | Subscription status |
| Device or other IDs (advertising ID) | Yes | Yes (Google AdMob) | Advertising | Consent via UMP in UK/EEA |
| App interactions / diagnostics | Yes (by AdMob SDK) | Yes (Google) | Advertising, analytics | SDK-collected |
Data is encrypted in transit: **Yes**. Users can request deletion: **Yes** (contact address in the privacy policy).

## 2. First release (manual, once)
1. Create an upload key on your own computer (keep it safe; Play App Signing holds the real signing key):
   `keytool -genkeypair -v -keystore aepx-upload.jks -alias aepx-upload -keyalg RSA -keysize 4096 -validity 9125`
2. Add GitHub secrets: `AEPX_UPLOAD_KEYSTORE_B64` (`base64 -w0 aepx-upload.jks`), `AEPX_UPLOAD_STORE_PASSWORD`,
   `AEPX_UPLOAD_KEY_ALIAS` (`aepx-upload`), `AEPX_UPLOAD_KEY_PASSWORD`. Add variables `AEPX_API_BASE_URL`, `AEPX_TENANT`,
   `AEPX_OIDC_ISSUER`, `AEPX_ANDROID_OIDC_CLIENT_ID`. Add reviewers to the `play-release` environment.
3. Once the IDE PRs are merged, run **Actions → Android companion release** with version code `1` and version name `0.2.0`
   and leave *upload to Play* unticked. Download `aepx-companion-0.2.0.aab` from the run.
4. Play Console → Testing → **Internal testing** → Create release → upload the `.aab` → add yourself as a tester → roll out.
5. Install from the internal-testing link and check sign-in, approvals, the plan card, ads (consent form first) and a
   test subscription (add your Google account under *License testing* so purchases are free).

## 3. Going to production
- **Organisation developer account** (Equality Software Ltd, verified with a D-U-N-S number): you can promote to production after review.
- **Personal developer account created after Nov 2023**: Google requires a closed test with at least 12 testers for 14 days
  before production access.
- Later versions: add the `AEPX_PLAY_SERVICE_ACCOUNT_JSON` secret, then run the release workflow with *upload to Play* ticked.
  It creates a draft on internal testing, which you promote in Play Console.

## 4. AdMob link-up
AdMob → Apps → `ca-app-pub-2980680946304710~2617421798` → **Link to Google Play** once the listing is live, and make sure
`https://www.softwareequality.com/app-ads.txt` is verified (see `../website/README.md`). The six ad units are already wired
into release builds (2 banners, interstitial, native, app open, rewarded ad-free break), and debug builds only use Google test ads.
