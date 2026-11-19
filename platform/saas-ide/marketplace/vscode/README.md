# AEP-X Agentic IDE for VS Code

A universal, governed agentic IDE: an AI agent crew plans and produces your work, you approve each step, and
every decision is audited. Start a project in any of nine IDEs that share one platform:

| IDE | What the agent crew does |
| --- | --- |
| Software | Architecture, code with file paths, tests, CI/CD |
| Sound | Cue sheets, effects, dialogue clean-up, mix and loudness plans |
| Music | Composition, arrangement, chord charts, rights checks |
| Movie & Film | Scripts, storyboards, shot lists, subtitles, edit plans |
| Animation | Keyframes, rigs, Blender and Lottie scripts |
| SDK | OpenAPI design, typed client libraries, API docs |
| Social Media | Campaigns, calendars, platform-specific posts (approval before publishing) |
| Multimedia | Cross-media launch kits and export pipelines |
| Media | Asset catalogues, metadata, rights and transcoding plans |

## Commands

- **AEP-X: Open Agentic IDE** (also the rocket button in the status bar)
- **AEP-X: New project (choose an IDE)**: opens the IDE's new-project dialog with that IDE selected
- **AEP-X: Plans and pricing**: 30-day free trial, then £4.99/month Pro (larger daily AI allowance and 95%
  fewer ads), or the free ad-supported plan

## Privacy and security

The extension reads no workspace files, stores no credentials and makes no network requests of its own; sign-in
and all agent work happen in the IDE. Roles (owner, admin, developer, media editor, reviewer, viewer) are
enforced on the server, and the audit trail is hash-chained. Self-hosted deployments can set `aepx.ideUrl`
(machine scope, HTTPS only).
