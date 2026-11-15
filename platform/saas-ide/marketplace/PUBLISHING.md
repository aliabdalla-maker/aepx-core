# Publishing the AEP-X plugins

Every `ide-vX.Y.Z` release builds the plugins with the release version and attaches them to the GitHub
release (`AEP-X-IDE-VSCode.vsix`, `AEP-X-IDE-JetBrains.zip`). The `marketplaces` job in
`.github/workflows/aepx-ide-release.yml` then lists them on each store **when that store's token exists**;
a missing token skips the store with a notice and never fails the release.

| Store | Listing id | One-time owner setup | Repository secret |
| --- | --- | --- | --- |
| Visual Studio Marketplace | `softwareequality.aepx-agentic-ide` | Create publisher `softwareequality` at marketplace.visualstudio.com/manage; create an Azure DevOps personal access token with scope *Marketplace → Manage* | `VSCE_PAT` |
| Open VSX (VSCodium, Cursor, Windsurf, Gitpod) | `softwareequality.aepx-agentic-ide` | Sign in at open-vsx.org with GitHub, sign the publisher agreement, create namespace `softwareequality`, create an access token | `OVSX_PAT` |
| JetBrains Marketplace | `com.softwareequality.aepx` | Create a vendor profile at plugins.jetbrains.com, upload the first `AEP-X-IDE-JetBrains.zip` by hand (JetBrains reviews new plugins), then create a permanent token | `JB_MARKETPLACE_TOKEN` (optional signing: `JB_CERTIFICATE_CHAIN`, `JB_PRIVATE_KEY`, `JB_PRIVATE_KEY_PASSWORD`) |
| Claude Code plugin marketplace | `aepx-ide@aepx` | None: listed in `.claude-plugin/marketplace.json` on `master` | — |

Install in Claude Code:

```
/plugin marketplace add aliabdalla-maker/aepx-core
/plugin install aepx-ide@aepx
```

After adding a token, re-run the `marketplaces` job of the latest release (Actions → AEP-X IDE release →
Re-run jobs) to publish without cutting a new version.
