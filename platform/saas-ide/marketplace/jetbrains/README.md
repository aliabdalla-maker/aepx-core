# JetBrains marketplace integration — implementation specification
Target: IntelliJ Platform plugin providing an **Open AEP-X Hybrid IDE** action.
Use JetBrains IntelliJ Platform Gradle Plugin 2.x, Kotlin, an AnAction registered in plugin.xml, and BrowserUtil.browse for `https://ide.softwareequality.com/`.
No editor filesystem, secrets, or network MCP dispatch privileges should be requested. Build against a supported IDE version and sign the plugin before marketplace upload. Plugin ID proposal: `com.softwareequality.aepx` (not registered).
This is a design scaffold, **not a compiled or published JetBrains plugin**.
