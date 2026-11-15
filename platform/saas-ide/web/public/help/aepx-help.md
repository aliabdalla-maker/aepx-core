# general | Getting started

## Signing in
Choose **Sign in with e-mail** on the welcome screen, or **Continue with Google** when your administrator has enabled Google sign-in. New users choose **Create an account**. Your session stays signed in while the tab is open; if it expires, your open tabs are kept and you are asked to sign in again.

## Password rules
Passwords must be 12 to 128 characters and contain an upper-case letter, a lower-case letter and a digit. A password cannot be the same as your username or e-mail address, and you cannot reuse your last three passwords. A long passphrase is the easiest strong choice. After 10 failed attempts the account is locked for a short, growing period. Accounts that sign in with Google use Google's password and two-step settings instead.

## Forgot password
Use **Forgot your password?** on the welcome screen or the sign-in page. A reset link is e-mailed to you. If the link is not shown, password reset by e-mail has not been enabled on this deployment yet.

## Two-step sign-in (authenticator app)
Open **Team → Password and two-step sign-in**, choose **Set up authenticator application**, scan the QR code with an app such as Google Authenticator or Microsoft Authenticator, and enter the 6-digit code. Recommended for owners and administrators.

## Linked accounts and devices
**Team → Linked Google / GitHub** connects or removes a social sign-in. **Team → Signed-in devices** lists active sessions and lets you sign out of any of them.

## Projects
Pick a project from the list at the top, or choose **New project** and the IDE module it belongs to (Software, Sound, Music, Film, Animation, SDK, Social, Multimedia or Media). Each module creates starter files for its work.

## Files and saving
Open files from the **Explorer**. Edits are kept in the tab until you choose **Save** (or press Ctrl/⌘+S). Save is greyed out when there is nothing to save; hover it to see why. Every save creates a version you can restore from the file history.

## Renaming, moving and deleting
Choose **Rename** above the editor to rename or move the open file: type a new name or a new path such as src/utils/helpers.py. Hover a folder in the Explorer for ✎ (rename or move the whole folder) and 🗑 (delete it). **New folder** (🗀) creates an empty folder. Nothing is lost: every renamed, moved or deleted file keeps its history and can be restored. A rename that would overwrite an existing file is refused.

## Searching a project
Type at least two characters in **Search files…** at the top of the Explorer. Matches in file names and saved file contents are listed with their line numbers; choose one to open the file at that line.

## Renaming and archiving projects
**Rename project** (owners, admins and developers) changes the project's name. **Archive** (owners and admins) hides a project without deleting anything; **Archived** lists archived projects and lets owners and admins restore them.

## Importing files
Choose **Import** in the Explorer. You can import individual files, a whole folder, or a .zip archive. Text files up to 1 MB each are imported (up to 300 files at a time); binary files and folders such as node_modules and .git are skipped and listed. Existing files are only overwritten when you tick **Replace existing files**. Each imported file is saved as a new version, so it can be undone from the file history.

## The assistant
The **Assistant** button (bottom right) is available on every screen. It answers from these help pages instantly and free of charge. When you are signed in with a project open and AI is enabled, **Ask AI** sends your question, the current module and the open file name to the AEP-X AI. You approve each AI request; it then counts against your daily AI allowance.

## AI agents
The **Agents** tab turns a task into a plan carried out by the module's agent crew. Review the plan, then **Approve & run**. Answers containing code show **Save to project** buttons. Nothing is executed or published without your approval.

## AI allowance and costs
Each plan has a daily AI allowance (free, trial or pro) and the platform has a monthly spending cap. When the allowance is used up, AI requests pause until midnight UTC; help answers keep working.

## Operations
The **Operations** tab is for owners and administrators. It shows MCP tool executions and lets you reconcile uncertain ones with a provider-signed receipt. It tells you when you are signed out, not allowed, or when the service is unreachable.

## Team and roles
Owners and admins can invite members and set roles. Viewers and reviewers are read-only. Media roles may only change media files (media/, audio/, music/, video/, film/).

## Installing the app
Choose **Install app** to add the IDE to your desktop or phone. Downloads for Windows, macOS, Linux and Android are on the downloads page.

## Which build am I on
The bottom bar shows **build** followed by the release identifier. If it shows separate web and api builds in orange, reload the page; if it persists, the deployment is incomplete.

# software | Software IDE

## What it is for
Code, tests, Git-ready projects, CI/CD pipelines and deployment plans, in any language. The editor provides syntax highlighting for common languages.

## Starter files
A new Software project starts with README.md. Add files with **New file** or bring existing code in with **Import** (a .zip of a repository works well).

## Using the agent crew
The architect, developer and tester agents plan and write code. Good tasks: "Build a FastAPI REST API with tests", "Add a GitHub Actions CI pipeline". Save the proposed files to the project, then review them in the editor.

## Checks on generated code
AI answers include an automatic validation report (syntax and common mistakes) under the code so you can review before saving.

# sound | Sound IDE

## What it is for
Dialogue, sound effects, restoration, mixing and mastering plans.

## Session editor
audio/session.json opens in a visual clip editor: open an audio file to see its waveform, set start and end, gain in dB and fade in/out for each clip, preview it, and export the edited clip as a WAV. Use **Code** to see the JSON.

## Cue sheets
audio/cue-sheet.md holds the cue list. Ask the agents to "Write a cue sheet for a 60s trailer".

## Loudness
For podcasts aim for about -16 LUFS integrated; ask "Plan a podcast mix to -16 LUFS" for a step-by-step chain.

# music | Music IDE

## What it is for
Composition, arrangement, MIDI, mixing and briefs for original AI music.

## Step sequencer
Any music/*.json file (for example music/song.json) opens in a step sequencer: set the tempo, give each track a note and waveform, click steps on or off, play it back, and **Export MIDI** (4 bars) for any DAW.

## Rights
The rights-checker agent flags samples or references that may need licences. Only original material should be published.

# film | Movie & Film IDE

## What it is for
Screenplays, storyboards, shot lists, edit decision lists and subtitles.

## Script
film/script.fountain uses the Fountain screenplay format (scene headings like INT. OFFICE - DAY, character names in capitals).

## Storyboard editor
film/storyboard.md opens as a shot table (Shot, Time, Description, Camera): add, reorder and time shots. **Export SRT** for subtitles or **Export EDL** for your editing software.

# animation | Animation IDE

## What it is for
2D/3D scenes, keyframes, rigs, motion and render plans.

## Keyframe editor
animation/*.json opens in a timeline: add objects, set keyframes for position, scale, rotation and opacity, scrub and preview, and export a self-contained HTML animation.

## Blender
Ask the agents for Blender Python scripts, for example "Write a Blender Python script for a bouncing logo", then run them in Blender yourself.

# sdk | SDK IDE

## What it is for
OpenAPI design, client libraries, API tests, versioning and documentation.

## OpenAPI editor
openapi.yaml opens in a visual editor: list and add operations (method, path, operation ID and summary), then generate a TypeScript or Python client from the spec.

## Versioning
Keep breaking changes in a new major version path (for example /v2) and record changes in a CHANGELOG.

# social | Social Media IDE

## What it is for
Campaigns, content calendars, drafts, approvals and analytics plans.

## Calendar editor
social/calendar.md opens as a calendar table (Date, Platform, Post, Status). Status moves through Draft, In review, Approved, Scheduled and Published. Nothing is posted automatically; you publish posts yourself after approval.

## Good tasks
"Plan a one-week launch campaign", "Write 5 TikTok captions with hashtags".

# multimedia | Multimedia IDE

## What it is for
Cross-media productions combining images, audio, video and slides.

## Manifest
media/manifest.json opens in the asset catalogue editor: list every deliverable with its title, type, tags, licence and source, and search it.

## Export pipelines
Ask "Write an ffmpeg pipeline for all export sizes" for a script that renders each format; run it on your own machine.

# media | Media IDE

## What it is for
Asset catalogue, metadata, rights, transcoding and distribution.

## Catalogue editor
assets/catalog.json opens as a searchable catalogue with title, type, tags, licence and source for each asset.

## Rights and licences
Ask the rights-manager agent to review the catalogue for missing licence or source information. Keep the licence source for every asset.
