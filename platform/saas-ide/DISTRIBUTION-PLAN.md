# AEP-X Hybrid IDE — multi-platform distribution

**Status: DRAFT / HOLD.** Nothing in this phase authorizes a live release.

## Implemented in the repository
- Web PWA manifest, install prompt, SVG icon and network-only service worker (no caching of workspace data or credentials).
- Electron desktop wrapper with strict approved HTTPS origin and sandboxed renderer.
- Manual GitHub Actions build matrix for draft Windows, macOS and Linux artifacts. It does not publish releases.
- Draft marketplace plugin manifest; this is not a submission to any external marketplace.

## Release targets
| Target | Packaging | Prerequisites |
| --- | --- | --- |
| Windows PC | Electron NSIS EXE, portable EXE | Signed code, SmartScreen testing, Windows QA |
| macOS Intel / Apple Silicon | DMG / ZIP | Apple Developer signing, notarization, Gatekeeper QA |
| Linux | AppImage, DEB, RPM | Linux architecture matrix, package signing and QA |
| Unix/BSD | Browser PWA where supported | Native installers require per-OS ports and tests; Linux packages are not universal Unix packages |
| Android | PWA first; Google Play requires a native Android AAB, e.g. TWA | Android project, verified HTTPS origin, Digital Asset Links, signing, store policy, testing |
| Marketplace plugin | Manifest is only a draft | Choose target marketplace, adapt its schema, permission review, vendor approval |

## Website distribution at softwareequality.com
The existing website needs a separately deployed downloads page and verified hosted artifacts.
Recommended route: `/products/aepx/download` with OS selection, signed binaries,
SHA-256 checksums, release notes, minimum system requirements, privacy policy and support links.
Never show active download buttons until actual signed artifacts have been uploaded and verified.
The IDE backend must be reachable over an approved HTTPS origin; desktop currently expects
`https://ide.softwareequality.com`. DNS and deployment are **not configured here**.

## Google Play
The provided Play Console URL is a private developer dashboard, not a public store listing.
Prepare a production Android package and signed AAB, upload to internal testing, complete
Data safety, content rating, privacy policy, target API and Play App Signing requirements,
then advance only after testing and review. No Play Console action has been performed.

## Marketplace
The destination marketplace is not yet specified (ChatGPT app/plugin directory, VS Code,
JetBrains, Chrome Web Store, or another provider). Each requires a different integration,
manifest and review process. No listing has been submitted.

## Release gates
1. All current AEP-X security CI checks green on final SHA.
2. Real signed binaries built and tested on each supported OS and architecture.
3. Desktop code signing and macOS notarization.
4. Domain ownership, DNS, HTTPS, OIDC redirects and download hosting verified.
5. Android build, upload-key custody, Play policy review and internal testing.
6. Marketplace-specific security review and explicit approval.
7. Independent security acceptance; keep live MCP dispatch disabled until signed off.

No automatic publication, deployment, merge, or live gateway forwarding.
