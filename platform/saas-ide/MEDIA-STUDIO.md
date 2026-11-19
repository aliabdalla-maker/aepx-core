# AEP-X Media Studio: agentic music, video, film, multimedia and social media

The Studio tab adds media work to the agentic IDE. When a task mentions music, video, film or social media, the agent crew gains a
**producer** (budget), **composer** (music/voice), **director** (script and storyboard), **editor** (timeline) and
**social manager** (posts). As with all agent work, the crew proposes and people approve.

| Capability | What it does |
| --- | --- |
| Templates | Starter projects with deploy files: web music player, browser video trimmer, social campaign, film pipeline |
| Generate | Image, video, music, voice and script jobs. Each job shows a cost estimate and runs only after approval |
| Film | Storyboard → scenes → shots → timeline in `media/storyboard.json`; export a CMX3600 EDL (Resolve, Premiere, Avid) or an ffmpeg render script |
| Social | Platform-aware drafts (character limits), approval, publish now or on schedule; YouTube, TikTok and Instagram produce upload packages |

## Governance
- Editors propose; **owners/admins approve** each paid generation and each public post. `IDE_MEDIA_FOUR_EYES=true` requires a different approver.
- An approval is bound to the SHA-256 digest of the exact content. **Editing a post voids its approval**; the database rejects an approval whose digest differs.
- Run and publish are single-use conditional updates, committed before any external call, so a job cannot be paid for twice and a post cannot go out twice.
- Every action goes to the append-only `ide_media_audit` table; the runtime role cannot update or delete audit rows.
- All tables are tenant-isolated with FORCE row-level security. Generated files are served with `sandbox` CSP and `nosniff`.

## Enabling providers (owner action; everything is off by default)
| Provider / platform | Enable with | Notes |
| --- | --- | --- |
| mock (free demo output) | `IDE_MEDIA_PROVIDERS_ENABLED=mock` | Safe for staging and demos |
| OpenAI: images, scripts | add `openai`, set `IDE_MEDIA_OPENAI_API_KEY` | Images stored as files (no expiring URLs) |
| ElevenLabs: voice, music | add `elevenlabs`, set `IDE_MEDIA_ELEVENLABS_API_KEY` (optional `_DEFAULT_VOICE`) | Check licence terms for commercial music use |
| Runway: video (image-to-video) | add `runway`, set `IDE_MEDIA_RUNWAY_API_KEY` | Needs a key frame (an image job); output links are temporary, so download them promptly |
| Mastodon | `IDE_SOCIAL_PLATFORMS_ENABLED=mastodon`, `IDE_SOCIAL_MASTODON_URL` (https), `IDE_SOCIAL_MASTODON_TOKEN` | |
| X | add `x`, `IDE_SOCIAL_X_USER_TOKEN` (OAuth 2.0 user token with tweet.write) | Paid X API tier required |
| LinkedIn | add `linkedin`, `IDE_SOCIAL_LINKEDIN_TOKEN`, `_AUTHOR_URN`, `_VERSION` (YYYYMM, a currently supported version) | |
| YouTube / TikTok / Instagram | add `youtube`, `tiktok`, `instagram` | Upload-package mode; direct API upload needs each platform's app review |

Scheduled posts: run `POST /api/v1/social-posts/publish-due` as an owner/admin from a scheduler (e.g. every 5 minutes).

## Not included yet
- Suno has no official public API, so it is not integrated; ElevenLabs Music covers AI music.
- Credentials are per deployment, not per user; per-user OAuth for social accounts is the next step.
- Media approvals are web-only for now. The Android and iOS companions cover plan and tool approvals.
