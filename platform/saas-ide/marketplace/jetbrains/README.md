# AEP-X Agentic IDE — JetBrains plugin

IntelliJ Platform plugin (IntelliJ IDEA, PyCharm, WebStorm, GoLand and other 2024.2+ IDEs) adding
**Tools | AEP-X | Open Agentic IDE** and **Plans and Pricing**. It reads no project files and stores no credentials.

Build and verify (CI: `distribution-checks.yml`): `gradle buildPlugin verifyPlugin test` (JDK 21).
The installable ZIP is written to `build/distributions/`.

Publishing is an **owner action** and is never run in CI:
1. Register the vendor "Equality Software Ltd" on plugins.jetbrains.com and reserve the ID `com.softwareequality.aepx`.
2. Create a plugin-signing certificate; set `JB_CERTIFICATE_CHAIN`, `JB_PRIVATE_KEY`, `JB_PRIVATE_KEY_PASSWORD`.
3. Run `gradle signPlugin`, upload the first version by hand; later versions may use `JB_MARKETPLACE_TOKEN` with `gradle publishPlugin`.
