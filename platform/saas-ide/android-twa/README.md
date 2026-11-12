# AEP-X Android Google Play package — implementation handoff

Use the existing HTTPS PWA at `https://ide.softwareequality.com` with Bubblewrap Trusted Web Activity (TWA). **An AAB has not been built or uploaded.**

Prerequisites: production HTTPS site, publicly accessible web manifest and icons (192x192 and 512x512 PNG required), verified Play Console app package, upload key and Play App Signing certificate SHA-256, privacy policy and Android QA.

Build procedure (on approved development machine):
1. `npm install --global @bubblewrap/cli`
2. `bubblewrap init --manifest https://ide.softwareequality.com/manifest.webmanifest`
3. Confirm application ID, minimum SDK, display name, icon assets and release settings.
4. `bubblewrap build` to create signed release artifacts using securely stored signing keys.
5. Publish `https://ide.softwareequality.com/.well-known/assetlinks.json` using the **Play app-signing** certificate SHA-256, not a guessed fingerprint.
6. Verify Digital Asset Links and app behaviour on Android, then upload AAB to **internal testing**, not production.

Never commit keystores, signing passwords, developer tokens or an invented `assetlinks.json`. No automatic Play Console submission.
