---
description: Create an AEP-X IDE project in one of the nine IDE modules
argument-hint: "<module> <project name>"
---

Create a project in the AEP-X Universal Agentic IDE using the aepx-ide skill.

Arguments: $ARGUMENTS — the first word is the module (software, sound, music, film, animation, sdk, social,
multimedia, media); the rest is the project name. If the module is missing or unknown, list the available
modules from `GET /api/v1/ide-modules` and ask which one.

Check that `AEPX_IDE_TOKEN` is set; if not, ask the user to sign in at https://ide.softwareequality.com and
provide a token. Open the personal workspace (`POST /api/v1/workspace`), create the project, then list its
starter files and give the link https://ide.softwareequality.com/.
