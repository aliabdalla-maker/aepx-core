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


SITE = "https://www.softwareequality.com"
PAGE_URL = SITE + "/aepx/"

# Styles are scoped under .aepx-page so the same markup can sit inside a WordPress theme unchanged.
CSS = """
.aepx-page{font:16px/1.55 Inter,system-ui,sans-serif;max-width:920px;margin:0 auto;padding:2rem 1.25rem;background:#0b1020;color:#e7ecf7;border-radius:16px}
.aepx-page a{color:#7acbff}.aepx-page .muted{color:#a9b4c8}
.aepx-page .hero{display:flex;gap:1.25rem;align-items:center;flex-wrap:wrap}
.aepx-page .hero img{width:96px;height:96px}
.aepx-page h1{margin:0;font-size:2.2rem;line-height:1.1;color:#e7ecf7}.aepx-page .tag{margin:.25rem 0 0;color:#7acbff;font-weight:600}
.aepx-page h2{color:#e7ecf7}.aepx-page .by{margin:.15rem 0 0;font-weight:600;letter-spacing:.02em}
.aepx-page section{border:1px solid #40506a;border-radius:10px;padding:.5rem 1.25rem;margin:1rem 0}
.aepx-page ul{list-style:none;padding:0;margin:0}
.aepx-page li{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:center;padding:.5rem 0;border-top:1px solid #1f2a40}
.aepx-page li:first-child{border-top:0}.aepx-page .name{flex:1 1 260px}
.aepx-page .btn{background:#2563eb;color:#fff;padding:.45rem .95rem;border-radius:6px;text-decoration:none;display:inline-block}
.aepx-page .btn:focus-visible,.aepx-page a:focus-visible{outline:3px solid #ffd166;outline-offset:2px}
.aepx-page .soon{color:#ffe08a}.aepx-page .sha{flex-basis:100%;font-size:.75rem;color:#a9b4c8;word-break:break-all}
.aepx-page .plans{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}
.aepx-page .plan{border:1px solid #40506a;border-radius:10px;padding:1rem}.aepx-page .plan h3{margin-top:0;color:#e7ecf7}
"""


def body(manifest: dict, assets: str = "") -> str:
    """Page content inside <div class="aepx-page">. `assets` prefixes logo URLs ("" = same folder)."""
    version = html.escape(str(manifest.get("version", "")))
    updated = html.escape(str(manifest.get("updated", "")))
    artifacts = manifest.get("artifacts") or []
    sections = []
    for key, title in SECTIONS:
        rows = [_row(a) for a in artifacts if a.get("platform") == key]
        if rows:
            sections.append(f'<section aria-labelledby="h-{key}"><h2 id="h-{key}">{title}</h2><ul>{"".join(rows)}</ul></section>\n')
    live = sum(1 for a in artifacts if is_live(a))
    a = html.escape(assets)
    return f"""<div class="aepx-page">
<div class="hero"><img src="{a}logo.svg" alt="AEP-X logo" width="96" height="96">
<div><h1>AEP-X Agentic IDE</h1><p class="tag">Agents plan. You approve. Every step audited.</p>
<p class="muted by">by Equality Software</p></div></div>
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
<p class="muted">{live} of {len(artifacts)} downloads available · <a href="{SITE}/aepx/privacy.html">Privacy policy</a> · Equality Software Ltd</p>
</div>"""


def render(manifest: dict, assets: str = "") -> str:
    """Standalone page (Hostinger / cPanel upload: public_html/aepx/index.html)."""
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Download AEP-X Agentic IDE | Software Equality</title>
<meta name="description" content="AEP-X Agentic IDE for Windows, macOS, Linux, Android, iPhone and iPad, VS Code and JetBrains. 30-day free trial, then £4.99/month or free with ads.">
<link rel="icon" href="{assets}favicon.ico" sizes="any"><link rel="icon" href="{assets}logo.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{assets}apple-touch-icon.png">
<link rel="canonical" href="{PAGE_URL}">
<meta property="og:title" content="AEP-X Agentic IDE"><meta property="og:description" content="Agents plan. You approve. Every step audited.">
<meta property="og:image" content="{PAGE_URL}og-image.png"><meta property="og:url" content="{PAGE_URL}"><meta name="theme-color" content="#0b1020">
<style>body{{margin:0;background:#0b1020}}{CSS}</style></head>
<body>
{body(manifest, assets)}
</body></html>
"""


def render_fragment(manifest: dict) -> str:
    """WordPress: paste into one "Custom HTML" block. Logo URLs point at the uploaded /aepx/ folder."""
    return f"""<!-- AEP-X downloads: paste into a WordPress Custom HTML block. Requires the /aepx/ folder from aepx-website-static.zip. -->
<style>{CSS}</style>
{body(manifest, SITE + "/aepx/")}
"""


# Authorised-sellers file for AdMob/AdSense. Must be served at the domain root: https://www.softwareequality.com/app-ads.txt
# (Google's seller account ID f08c47fec0942fa0 is the same for every publisher.)
APP_ADS_TXT = "google.com, pub-2980680946304710, DIRECT, f08c47fec0942fa0\n"

PRIVACY_BODY = """<div class="aepx-page">
<div class="hero"><img src="{assets}logo.svg" alt="AEP-X logo" width="64" height="64"><div><h1>AEP-X privacy policy</h1>
<p class="tag">AEP-X Agentic IDE: web, desktop, Android, iOS and editor plugins</p></div></div>
<p class="muted">Last updated: {updated}. Provider: Equality Software Ltd, London, United Kingdom ("we").</p>
<section><h2>What we collect and why</h2><ul>
<li><span class="name"><strong>Account</strong>: the identifier and profile your organisation's sign-in provider gives us, to sign you in and keep your workspace separate from others.</span></li>
<li><span class="name"><strong>Your work</strong>: projects, files, agent plans, approvals and audit records you create, so the service works and every decision is traceable.</span></li>
<li><span class="name"><strong>Subscription</strong>: your plan, trial dates and the store's subscription reference (Stripe, Google Play or the App Store). Card details are handled by those stores, never by us.</span></li>
<li><span class="name"><strong>Media Studio (optional)</strong>: prompts and files you approve for generation or posting are sent to the provider or social network you choose, only after an owner or admin approves each one.</span></li>
</ul></section>
<section><h2>Advertising</h2>
<p>The free trial and free plan show ads from Google (AdMob in the mobile apps, AdSense on the web). Google may use device identifiers or cookies to serve and measure ads.
In the UK, EEA and Switzerland we ask for your consent first with Google's consent tool, and you can change your choice at any time from <em>Privacy options</em> in the app.
Without consent, only limited, non-personalised ads are shown. Approval screens never show ads. Learn how Google uses data at
<a href="https://policies.google.com/technologies/partner-sites">policies.google.com/technologies/partner-sites</a>.</p></section>
<section><h2>Sharing</h2><p>We do not sell personal data. We share it only with the processors needed to run the service (hosting, payment stores, Google for ads, and any media provider you choose), or when the law requires it.</p></section>
<section><h2>Retention and security</h2><p>Workspace data is kept while your account is active and deleted on request or when your organisation closes its account, except audit and billing records we must keep by law.
Data is encrypted in transit and isolated per organisation.</p></section>
<section><h2>Your rights</h2><p>Under UK GDPR you can ask to access, correct, export or delete your data, and object to or restrict processing. You can also complain to the Information Commissioner's Office (ico.org.uk).</p></section>
<section><h2>Children</h2><p>AEP-X is a professional tool and is not directed at children under 16.</p></section>
<section><h2>Contact</h2><p>Email <a href="mailto:privacy@softwareequality.com">privacy@softwareequality.com</a>, or write to Equality Software Ltd, London, United Kingdom.</p></section>
</div>"""


def render_privacy(updated: str, fragment: bool = False) -> str:
    content = PRIVACY_BODY.format(assets=(SITE + "/aepx/") if fragment else "", updated=html.escape(updated))
    if fragment:
        return f"<!-- AEP-X privacy policy: paste into a WordPress Custom HTML block. -->\n<style>{CSS}</style>\n{content}\n"
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy policy | AEP-X Agentic IDE</title><link rel="icon" href="favicon.ico" sizes="any">
<link rel="canonical" href="{PAGE_URL}privacy.html"><style>body{{margin:0;background:#0b1020}}{CSS}</style></head>
<body>
{content}
</body></html>
"""


def main() -> None:
    here = Path(__file__).parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=here / "releases.json")
    parser.add_argument("--check", action="store_true", help="fail if any committed page is out of date")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    outputs = {
        here / "website-downloads.html": render(manifest),
        here / "website" / "static" / "aepx" / "index.html": render(manifest),
        here / "website" / "wordpress" / "aepx-downloads-block.html": render_fragment(manifest),
        here / "website" / "static" / "aepx" / "privacy.html": render_privacy(manifest["updated"]),
        here / "website" / "wordpress" / "aepx-privacy-block.html": render_privacy(manifest["updated"], fragment=True),
        here / "website" / "static" / "app-ads.txt": APP_ADS_TXT,
    }
    for path, page in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != page:
                raise SystemExit(f"{path} is stale: run generate_downloads.py")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page, encoding="utf-8")
            print(f"wrote {path}")
    if args.check:
        print("website pages up to date")


if __name__ == "__main__":
    main()
