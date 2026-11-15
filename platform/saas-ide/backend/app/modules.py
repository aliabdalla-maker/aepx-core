"""IDE module registry (spec §2-4): specialised workspaces sharing one core platform.

Each module reuses the same auth, ACL, agents, files, audit and billing. A module adds a starter
project layout, an agent crew and quick tasks. Modules marked "planned" are listed so the roadmap
is visible, but cannot be selected for new projects until their engines exist.
"""

def _m(id, name, summary, crew, starter, tasks, status="available"):
    return {"id": id, "name": name, "summary": summary, "status": status,
            "crew": [{"agent": a, "goal": g} for a, g in crew],
            "starter_files": starter, "quick_tasks": tasks}


MODULES = [
    _m("software", "Software IDE", "Code, tests, Git-ready projects, CI/CD and deployment plans.",
       [("architect", "Design modules, APIs and security boundaries"),
        ("developer", "Write the code with file paths"),
        ("tester", "Write unit and integration tests")],
       {"README.md": "# New project\n\nDescribe what you are building, then ask the agents.\n"},
       ["Build a FastAPI REST API with tests", "Add a GitHub Actions CI pipeline", "Review this project for security issues"]),
    _m("sound", "Sound IDE", "Dialogue, sound effects, restoration, mixing and mastering plans.",
       [("sound-designer", "Design effects and ambience cue by cue"),
        ("mix-engineer", "Plan levels, EQ, compression and loudness targets"),
        ("restoration", "Propose noise reduction and repair steps")],
       {"audio/session.json": '{\n  "sample_rate": 48000,\n  "tracks": [],\n  "loudness_target_lufs": -16\n}\n',
        "audio/cue-sheet.md": "# Cue sheet\n\n| Time | Cue | Notes |\n|---|---|---|\n"},
       ["Write a cue sheet for a 60s trailer", "Plan a podcast mix to -16 LUFS", "Give an ffmpeg chain to clean noisy dialogue"]),
    _m("music", "Music IDE", "Composition, arrangement, MIDI, mixing and original AI music briefs.",
       [("composer", "Write melody, harmony and structure"),
        ("arranger", "Assign instruments and parts per section"),
        ("rights-checker", "Flag copyright and licensing risks")],
       {"music/song.json": '{\n  "title": "Untitled",\n  "tempo_bpm": 120,\n  "key": "C major",\n  "sections": []\n}\n'},
       ["Compose a 30s upbeat electronic piece", "Write chord charts for verse and chorus", "Create a music generation prompt"]),
    _m("film", "Movie & Film IDE", "Screenplays, storyboards, shot lists, edit decision lists and subtitles.",
       [("screenwriter", "Write or revise the script"),
        ("director", "Storyboard shots with timings and camera moves"),
        ("editor", "Assemble the edit and export an EDL or ffmpeg script")],
       {"film/script.fountain": "Title: Untitled\n\nINT. LOCATION - DAY\n\nAction.\n",
        "film/storyboard.md": "# Storyboard\n\n| Shot | Time | Description | Camera |\n|---|---|---|---|\n"},
       ["Storyboard a 60s product film", "Write subtitles (SRT) for this script", "Plan the edit with an ffmpeg command"]),
    _m("animation", "Animation IDE", "2D/3D scenes, keyframes, rigs, motion and render plans.",
       [("animator", "Block keyframes and timing"),
        ("rigger", "Define rigs and constraints"),
        ("technical-artist", "Write scene and render scripts")],
       {"animation/scene.json": '{\n  "fps": 24,\n  "frames": 240,\n  "objects": [],\n  "keyframes": []\n}\n'},
       ["Write a Blender Python script for a bouncing logo", "Keyframe a 10s character walk cycle", "Write a Lottie animation JSON"]),
    _m("sdk", "SDK IDE", "OpenAPI design, client libraries, API tests, versioning and docs.",
       [("api-designer", "Design and validate the OpenAPI contract"),
        ("sdk-generator", "Generate typed client libraries"),
        ("doc-writer", "Write reference docs and examples")],
       {"openapi.yaml": "openapi: 3.1.0\ninfo:\n  title: My API\n  version: 0.1.0\npaths: {}\n"},
       ["Design an OpenAPI spec for a bookings API", "Generate a TypeScript client from openapi.yaml", "Write API contract tests"]),
    _m("social", "Social Media IDE", "Campaigns, calendars, drafts, approvals and analytics plans.",
       [("strategist", "Plan the campaign and calendar"),
        ("copywriter", "Draft posts per platform"),
        ("moderator", "Check claims, rights and platform policies")],
       {"social/calendar.md": "# Content calendar\n\n| Date | Platform | Post | Status |\n|---|---|---|---|\n"},
       ["Plan a one-week launch campaign", "Write 5 TikTok captions with hashtags", "Draft a LinkedIn announcement"]),
    _m("multimedia", "Multimedia IDE", "Cross-media productions combining image, audio, video and slides.",
       [("producer", "Plan deliverables, budgets and schedule"),
        ("media-engineer", "Plan transforms and exports per format")],
       {"media/manifest.json": '{\n  "deliverables": [],\n  "assets": []\n}\n'},
       ["Plan a launch kit: video, audio ad, images", "Write an ffmpeg pipeline for all export sizes"]),
    _m("media", "Media IDE", "Asset catalogue, metadata, rights, transcoding and distribution.",
       [("librarian", "Classify, tag and catalogue assets"),
        ("rights-manager", "Track licences and usage rights")],
       {"assets/catalog.json": '{\n  "assets": []\n}\n'},
       ["Design a metadata schema for our video library", "Plan transcoding presets for web and mobile"]),
]

PLANNED = [
    ("agent", "AI & Agent IDE"), ("game", "Game Development IDE"), ("3d", "3D Modelling IDE"),
    ("xr", "AR/VR/XR IDE"), ("data", "Data Science IDE"), ("security", "Cybersecurity IDE"),
    ("iot", "IoT IDE"), ("automation", "Automation IDE"), ("web-design", "Web Design IDE"),
    ("mobile", "Mobile IDE"), ("database", "Database IDE"), ("docs", "Documentation IDE"),
    ("education", "Education IDE"), ("robotics", "Robotics IDE"), ("podcast", "Podcast IDE"),
    ("broadcast", "Broadcasting IDE"),
]

AVAILABLE = {m["id"]: m for m in MODULES}


def registry() -> list[dict]:
    return MODULES + [{"id": i, "name": n, "status": "planned", "summary": "On the roadmap.",
                       "crew": [], "starter_files": {}, "quick_tasks": []} for i, n in PLANNED]


def module_or_default(module_id: str | None) -> dict:
    return AVAILABLE.get(module_id or "software", AVAILABLE["software"])


def crew_steps(module_id: str | None) -> list[dict]:
    if not module_id or module_id == "software":
        return []
    return [{"agent": c["agent"], "action": "produce", "goal": c["goal"]}
            for c in module_or_default(module_id)["crew"]]
