"""Render the softwareequality.com downloads page from releases.json.

Fail-closed publishing rule: an artifact gets a live download button only when it is signed, has a
SHA-256 checksum, a byte size, and an https URL on an approved host. Store and marketplace entries need
only an https URL on their store's host. Everything else renders as "Coming soon", so the page can be
deployed before any binary exists without ever offering an unverified download.

The page is static HTML with no scripts, so it works under a strict CSP.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

DOWNLOAD_HOSTS = {"downloads.softwareequality.com"}
STORE_HOSTS = {
    "play.google.com", "apps.apple.com", "marketplace.visualstudio.com", "plugins.jetbrains.com",
}
SECTIONS = [
    ("windows", "Windows (PC)"), ("macos", "macOS"), ("linux", "Linux"), ("unix", "Unix-like systems"),
    ("android", "Android"), ("store", "App stores"), ("plugin", "Editor plugins"),
]
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _https_on(url: object, hosts: set[str]) -> bool:
    if not isinstance(url, str):
        return False
    u = urlparse(url)
    return u.scheme == "https" and u.hostname in hosts and not u.username and not u.password and u.port is None


def is_live(a: dict) -> bool:
    if a.get("platform") in ("store", "plugin"):
        return _https_on(a.get("url"), STORE_HOSTS)
    return (a.get("signed") is True
            and isinstance(a.get("sha256"), str) and bool(SHA256.match(a["sha256"]))
            and isinstance(a.get("bytes"), int) and a["bytes"] > 0
            and _https_on(a.get("url"), DOWNLOAD_HOSTS)
            and isinstance(a.get("filename"), str) and Path(a["filename"]).name == a["filename"])


def _row(a: dict) -> str:
    e = html.escape
    label = e(str(a.get("label", "")))
    if not is_live(a):
        return f'<li><span class="name">{label}</span><span class="soon">Coming soon</span></li>'
    if a["platform"] in ("store", "plugin"):
        return f'<li><span class="name">{label}</span><a class="btn" href="{e(a["url"])}" rel="noopener">Open</a></li>'
    mb = a["bytes"] / 1_000_000
    return (f'<li><span class="name">{label}</span>'
            f'<a class="btn" href="{e(a["url"])}" download>Download ({mb:.0f} MB)</a>'
            f'<code class="sha" title="SHA-256">SHA-256 {e(a["sha256"])}</code></li>')


def render(manifest: dict) -> str:
    version = html.escape(str(manifest.get("version", "")))
    updated = html.escape(str(manifest.get("updated", "")))
    artifacts = manifest.get("artifacts") or []
    sections = []
    for key, title in SECTIONS:
        rows = [_row(a) for a in artifacts if a.get("platform") == key]
        if rows:
            sections.append(f'<section aria-labelledby="h-{key}"><h2 id="h-{key}">{title}</h2><ul>{"".join(rows)}</ul></section>\n')
    live = sum(1 for a in artifacts if is_live(a))
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Download AEP-X Agentic IDE | Software Equality</title>
<meta name="description" content="AEP-X Agentic IDE for Windows, macOS, Linux, Android, iPhone and iPad, VS Code and JetBrains. 30-day free trial, then £4.99/month or free with ads.">
<style>
body{{font:16px/1.5 system-ui,sans-serif;margin:0 auto;max-width:900px;padding:2rem 1.25rem;background:#0b1020;color:#e7ecf7}}
a{{color:#7acbff}}h1{{margin-bottom:.25rem}}.muted{{color:#a9b4c8}}
section{{border:1px solid #40506a;border-radius:10px;padding:.5rem 1.25rem;margin:1rem 0}}
ul{{list-style:none;padding:0}}li{{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;padding:.5rem 0;border-top:1px solid #1f2a40}}
li:first-child{{border-top:0}}.name{{flex:1 1 260px}}
.btn{{background:#2563eb;color:#fff;padding:.4rem .9rem;border-radius:6px;text-decoration:none}}
.btn:focus-visible{{outline:3px solid #ffd166;outline-offset:2px}}
.soon{{color:#ffe08a}}.sha{{flex-basis:100%;font-size:.75rem;color:#a9b4c8;word-break:break-all}}
.plans{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}}
.plan{{border:1px solid #40506a;border-radius:10px;padding:1rem}}.plan h3{{margin-top:0}}
</style></head>
<body>
<h1>AEP-X Agentic IDE</h1>
<p class="muted">Version {version} · updated {updated}</p>
<p>Plan work with an agent crew, approve every step, and keep a full audit trail: in your browser, on your desktop, on your phone, or inside your editor.
Use it now on the web at <a href="https://ide.softwareequality.com/">ide.softwareequality.com</a>.</p>

<section id="pricing" aria-labelledby="h-pricing"><h2 id="h-pricing">Plans</h2>
<div class="plans">
<div class="plan"><h3>Free trial</h3><p><strong>30 days free</strong>. Every feature, ad-supported.</p></div>
<div class="plan"><h3>Pro</h3><p><strong>£4.99/month</strong>. 95% fewer ads. Cancel any time.</p></div>
<div class="plan"><h3>Free</h3><p><strong>£0</strong> after the trial. Keep working, with ads.</p></div>
</div>
<p class="muted">One account works everywhere. Subscribe on the web, in the Android app (Google Play) or in the iOS apps (App Store).</p>
</section>

{"".join(sections)}
<section aria-labelledby="h-verify"><h2 id="h-verify">Verify your download</h2>
<p>Compare the SHA-256 shown above with your file: <code>sha256sum FILE</code> (Linux), <code>shasum -a 256 FILE</code> (macOS) or
<code>Get-FileHash FILE</code> (Windows PowerShell). Installers are code-signed; never run a file whose checksum does not match.</p>
<p class="muted">Unix-like systems: the tarball runs on 64-bit Linux distributions. BSD and other Unix systems can use the web IDE in a modern browser.</p>
</section>
<p class="muted">{live} of {len(artifacts)} downloads available · <a href="https://www.softwareequality.com/privacy">Privacy</a> · <a href="https://www.softwareequality.com/terms">Terms</a></p>
</body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("releases.json"))
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("website-downloads.html"))
    parser.add_argument("--check", action="store_true", help="fail if the committed page is out of date")
    args = parser.parse_args()
    page = render(json.loads(args.manifest.read_text(encoding="utf-8")))
    if args.check:
        if args.out.read_text(encoding="utf-8") != page:
            raise SystemExit(f"{args.out} is stale: run generate_downloads.py")
        print("downloads page up to date")
    else:
        args.out.write_text(page, encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
