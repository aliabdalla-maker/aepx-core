"""Starter projects for media apps. Applying a template only creates files that do not exist yet."""
from __future__ import annotations

import json

_NGINX_DOCKERFILE = """# Static deploy: docker build -t my-media-app . && docker run -p 8080:8080 my-media-app
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --chown=nginx:nginx . /usr/share/nginx/html
EXPOSE 8080
"""

_STORYBOARD = {
    "title": "Launch film",
    "logline": "A two-minute story of a team shipping its first agentic product.",
    "fps": 25,
    "soundtrack_job_id": None,
    "scenes": [
        {"id": "s1", "title": "Dawn in the city", "script": "EXT. CITY - DAWN. The skyline wakes up.",
         "shots": [{"id": "s1-wide", "description": "Wide aerial of the skyline at sunrise", "duration_s": 5, "media_job_id": None}]},
        {"id": "s2", "title": "The studio", "script": "INT. STUDIO - DAY. The team approves the agent's plan.",
         "shots": [{"id": "s2-desk", "description": "Close-up of hands approving a plan on a laptop", "duration_s": 5, "media_job_id": None}]},
    ],
    "timeline": [{"shot_id": "s1-wide", "start_s": 0, "end_s": 5}, {"shot_id": "s2-desk", "start_s": 5, "end_s": 10}],
}

TEMPLATES: dict[str, dict] = {
    "music-player": {
        "title": "Music player (web)",
        "description": "Accessible web audio player with a JSON playlist and keyboard controls.",
        "files": {
            "index.html": """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Player</title><link rel="stylesheet" href="style.css"></head>
<body><main><h1>Player</h1>
<ol id="playlist" aria-label="Playlist"></ol>
<audio id="audio" controls preload="none"></audio>
<p class="hint">Space: play/pause · N: next · P: previous</p></main>
<script src="player.js" type="module"></script></body></html>
""",
            "style.css": "body{font:16px system-ui;background:#0b1020;color:#e7ecf7;margin:2rem}button{font:inherit}"
                         "li button[aria-current=true]{font-weight:700}audio{width:100%}\n",
            "player.js": """const audio = document.getElementById("audio");
const list = document.getElementById("playlist");
const tracks = await (await fetch("playlist.json")).json();
let index = 0;
function play(i) {
  index = (i + tracks.length) % tracks.length;
  audio.src = tracks[index].src;
  list.querySelectorAll("button").forEach((b, n) => b.setAttribute("aria-current", String(n === index)));
  void audio.play();
}
tracks.forEach((t, i) => {
  const li = document.createElement("li"), b = document.createElement("button");
  b.textContent = `${t.title} — ${t.artist}`; b.onclick = () => play(i); li.append(b); list.append(li);
});
audio.addEventListener("ended", () => play(index + 1));
document.addEventListener("keydown", (e) => {
  if (e.target instanceof HTMLButtonElement) return;
  if (e.key === " ") { e.preventDefault(); audio.paused ? void audio.play() : audio.pause(); }
  if (e.key === "n") play(index + 1);
  if (e.key === "p") play(index - 1);
});
""",
            "playlist.json": json.dumps([{"title": "Studio theme", "artist": "AEP-X Studio", "src": "media/theme.mp3"}], indent=2) + "\n",
            "Dockerfile": _NGINX_DOCKERFILE,
            "README.md": "# Music player\n\nAdd tracks to `media/` (or generate one in the Studio tab with a *music* job) "
                         "and list them in `playlist.json`. Deploy with the Dockerfile to any container host.\n",
        },
    },
    "video-editor": {
        "title": "Video trimmer (web)",
        "description": "Browser video trimmer: mark in/out points, export an edit list for ffmpeg.",
        "files": {
            "index.html": """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trimmer</title></head><body style="font:16px system-ui;background:#0b1020;color:#e7ecf7;margin:2rem">
<h1>Trimmer</h1><label>Video file <input type="file" id="file" accept="video/*"></label>
<video id="video" controls style="width:100%;max-height:60vh"></video>
<p><button id="in">Mark in</button> <button id="out">Mark out</button> <button id="export">Export edit list</button></p>
<pre id="cuts" aria-live="polite"></pre><script src="editor.js" type="module"></script></body></html>
""",
            "editor.js": """const video = document.getElementById("video"), cuts = [];
let start = null;
document.getElementById("file").onchange = (e) => { const f = e.target.files[0]; if (f) video.src = URL.createObjectURL(f); };
document.getElementById("in").onclick = () => { start = video.currentTime; };
document.getElementById("out").onclick = () => {
  if (start === null || video.currentTime <= start) return;
  cuts.push({ start: +start.toFixed(2), end: +video.currentTime.toFixed(2) }); start = null; render();
};
function render() { document.getElementById("cuts").textContent = JSON.stringify(cuts, null, 2); }
document.getElementById("export").onclick = () => {
  // ffmpeg -i input.mp4 -ss START -to END -c copy part-N.mp4, then concat (see README)
  const lines = cuts.map((c, i) => `ffmpeg -i input.mp4 -ss ${c.start} -to ${c.end} -c copy part-${i}.mp4`);
  const blob = new Blob([lines.join("\\n") + "\\n"], { type: "text/plain" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "cuts.sh" });
  a.click();
};
""",
            "Dockerfile": _NGINX_DOCKERFILE,
            "README.md": "# Video trimmer\n\nRuns entirely in the browser (the video never leaves the device). "
                         "Exported `cuts.sh` uses ffmpeg; join parts with `ffmpeg -f concat -i list.txt -c copy out.mp4`.\n",
        },
    },
    "social-scheduler": {
        "title": "Social campaign",
        "description": "Campaign calendar as data; posts are drafted, approved and published from the Studio tab.",
        "files": {
            "campaign.json": json.dumps({"name": "Launch week", "posts": [
                {"platform": "linkedin", "day": 1, "text": "We're launching AEP-X Studio: agents that plan, you approve."},
                {"platform": "x", "day": 1, "text": "Agents plan. You approve. Every step audited. #AEPX"},
                {"platform": "youtube", "day": 3, "text": "Launch film: how we ship with governed agents.", "media": "film"}]}, indent=2) + "\n",
            "README.md": "# Social campaign\n\nAsk the agent crew to turn `campaign.json` into Studio drafts. Nothing is "
                         "posted until an owner/admin approves each post; YouTube/TikTok/Instagram posts are exported "
                         "as upload packages.\n",
        },
    },
    "film-pipeline": {
        "title": "Film / video pipeline",
        "description": "Storyboard → script → shots → timeline, with AI generation per shot and EDL export.",
        "files": {
            "media/storyboard.json": json.dumps(_STORYBOARD, indent=2) + "\n",
            "README.md": "# Film pipeline\n\n1. Edit the storyboard in the Studio tab (or `media/storyboard.json`).\n"
                         "2. Generate a script, then a key frame (image) and clip (video) per shot; each job needs approval.\n"
                         "3. Arrange clips on the timeline and export an EDL (for Resolve/Premiere) or an ffmpeg script.\n",
        },
    },
}


def listing() -> list[dict]:
    return [{"id": k, "title": v["title"], "description": v["description"], "files": sorted(v["files"])}
            for k, v in TEMPLATES.items()]
