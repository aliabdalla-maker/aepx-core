# AEP-X for iPhone and iPad

Two App Store apps share one core package (`AEPXKit`, unit-tested with `swift test`):

| App | Bundle ID | What it is |
| --- | --- | --- |
| **AEP-X** (`AEPXCompanion`) | `com.equalitysoftware.aepx.companion` | Native SwiftUI companion: sign in, projects, runs, plan and tool-call approvals (ad-free approval screens), banner and interstitial ads, Pro subscription |
| **AEP-X IDE** (`AEPXIDE`) | `com.equalitysoftware.aepx.ide` | The full web IDE in a locked-down WKWebView, with StoreKit for subscriptions |

## Plans on iOS
Same rules as web and Android, decided by the backend: 30-day free trial with full ads, then £4.99/month
Pro (95% fewer ads) or the free ad-supported plan. On iOS the subscription is sold with **StoreKit 2**
(App Store rule 3.1.1). Each purchase carries `appAccountToken = account_id`; the backend checks it with the
App Store Server API (`POST /api/v1/billing/app-store/verify`). Stripe pages are blocked in the wrapper.

## Build
```
brew install xcodegen
cd platform/saas-ide/ios && xcodegen generate && open AEPX.xcodeproj
```
CI (`ios-apps.yml`) runs `swift test` and unsigned simulator builds of both apps.

## Owner actions before TestFlight / App Store (not done by CI)
1. Apple Developer Program: register both bundle IDs; set `AEPX_TEAM_ID` in `Config/Local.xcconfig`.
2. App Store Connect: create both apps, and in each an auto-renewable subscription at **£4.99/month**
   (product IDs in `Config/Base.xcconfig`); no App Store free-trial offer (the 30-day trial is ours).
3. Backend env: `APPLE_BUNDLE_ID=com.equalitysoftware.aepx.companion,com.equalitysoftware.aepx.ide`,
   `APPLE_PRODUCT_ID` with the two product IDs in the same order, `APPLE_ISSUER_ID`, `APPLE_KEY_ID`,
   `APPLE_PRIVATE_KEY_FILE`, `APPLE_ROOT_CA_SHA256`, `APPLE_ENVIRONMENT=sandbox` for TestFlight.
4. AdMob: create **iOS** apps in AdMob (the Android app ID cannot be reused), then set `AEPX_ADMOB_APP_ID`,
   `AEPX_ADMOB_BANNER_UNIT`, `AEPX_ADMOB_INTERSTITIAL_UNIT`, and register the wrapper's web view domain.
5. OIDC: register redirect `com.equalitysoftware.aepx.companion:/oauth2redirect`; set issuer, client ID,
   and `AEPX_IDP_ORIGINS` for the wrapper.
6. Archive, upload to TestFlight, complete App Privacy (`Resources/PrivacyInfo.xcprivacy`) and review.
