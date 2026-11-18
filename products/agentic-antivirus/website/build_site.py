"""Builds the Agentic Antivirus pages for www.softwareequality.com/apps/agentic-antivirus/ (DST-01).
Static HTML, no scripts (works under a strict CSP). Download/store buttons use the same fail-closed
rule as the AEP-X IDE site (platform/saas-ide/distribution/generate_downloads.is_live).
Outputs: website/dist/static/... (upload into public_html), website/dist/wordpress/*.html, and a zip."""
import html
import json
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = HERE.parent
REPO = P.parents[1]
sys.path.insert(0, str(REPO / "platform" / "saas-ide" / "distribution"))
from generate_downloads import is_live  # noqa: E402

SITE = "https://www.softwareequality.com"
BASE = "/apps/agentic-antivirus/"
OUT = HERE / "dist"
SECTIONS = [("windows", "Windows"), ("macos", "macOS"), ("linux", "Linux"), ("store", "Phones and tablets")]

CSS = """
.aav{--ink:#17212b;--muted:#556270;--line:#d5dce3;--bg:#eef1f4;--amber:#8a4f00;font:400 1.0625rem/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--bg);margin:0}
.aav main{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
.aav header{display:flex;gap:.75rem;align-items:center}
.aav h1{font-size:2.25rem;line-height:1.15;margin:1.5rem 0 .5rem;max-width:22ch}
.aav h2{font-size:1.375rem;margin:2.5rem 0 .75rem}
.aav p,.aav li{max-width:68ch}
.aav .lede{font-size:1.2rem;color:var(--muted)}
.aav .status{border:1px solid var(--amber);border-inline-start:6px solid var(--amber);background:#fff4e0;padding:.8rem 1rem;border-radius:8px}
.aav .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:1rem}
.aav .card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:1rem 1.2rem}
.aav .card h3{margin:.2rem 0 .4rem;font-size:1.1rem}
.aav ul.dl{list-style:none;padding:0;margin:0}
.aav ul.dl li{display:flex;justify-content:space-between;gap:1rem;padding:.45rem 0;border-bottom:1px solid var(--line)}
.aav .soon{color:var(--muted)}
.aav .btn{background:var(--ink);color:#fff;padding:.3rem .8rem;border-radius:6px;text-decoration:none}
.aav table{border-collapse:collapse;width:100%;background:#fff}
.aav th,.aav td{border:1px solid var(--line);padding:.5rem .7rem;text-align:start;vertical-align:top}
.aav a{color:inherit}
.aav footer{margin-top:3rem;color:var(--muted);font-size:.95rem}
"""


def row(a):
    e = html.escape
    if not is_live(a):
        return f'<li><span>{e(a["label"])}</span><span class="soon">Coming soon</span></li>'
    if a["platform"] == "store":
        return f'<li><span>{e(a["label"])}</span><a class="btn" href="{e(a["url"])}" rel="noopener">Open</a></li>'
    return (f'<li><span>{e(a["label"])}</span><a class="btn" href="{e(a["url"])}" download>Download</a> '
            f'<code>SHA-256 {e(a["sha256"])}</code></li>')


def product_body(m):
    dl = "".join(f'<div class="card"><h3>{t}</h3><ul class="dl">{"".join(row(a) for a in m["artifacts"] if a["platform"] == k)}</ul></div>'
                 for k, t in SECTIONS)
    return f"""<main>
<header><img src="{BASE}icon.svg" alt="" width="40" height="40"><strong>Agentic Antivirus</strong></header>
<h1>Antivirus and threat response with a person in charge of every decision</h1>
<p class="lede">Agentic Antivirus scans and quarantines malware on your computers, watches for ransomware and stolen-credential behaviour, and uses an AI assistant to explain incidents with evidence. Anything that changes a device, an account or your traffic waits for an approval from your team.</p>
<p class="status"><strong>Early access.</strong> Version {html.escape(m["version"])} is in testing and not yet available to install. Downloads will appear here once signed builds have passed release checks. To join early access, email <a href="mailto:support@softwareequality.com?subject=Agentic%20Antivirus%20early%20access">support@softwareequality.com</a>.</p>

<h2>What it does</h2>
<div class="grid">
<div class="card"><h3>Stops known malware</h3><p>Scans files on demand, on a schedule and when they arrive. Known threats go to an encrypted quarantine where they cannot run. A file comes back only after an administrator gives a reason and a fresh scan finds it clean.</p></div>
<div class="card"><h3>Catches suspicious behaviour</h3><p>Flags encoded scripts, credential dumping, mass file encryption, deleted backups and misuse of admin tools, and links every alert to the events behind it.</p></div>
<div class="card"><h3>Explains incidents with evidence</h3><p>The assistant groups related alerts into a timeline, separates what was observed from what is suspected, and lists what evidence is missing. It can suggest actions but never approve them.</p></div>
<div class="card"><h3>Keeps you in control</h3><p>Stopping processes, isolating devices and changing traffic rules need an approval that covers one action, its exact targets and a limited time. Every step is recorded in a tamper-evident audit trail.</p></div>
<div class="card"><h3>Works offline</h3><p>Devices keep enforcing their last verified, signed policy without a connection, buffer events, and send them when they reconnect.</p></div>
<div class="card"><h3>Watches your public services</h3><p>Tracks every internet-facing endpoint, shows when your DDoS provider is mitigating an attack, and alerts on services with no protection.</p></div>
</div>

<h2>Pricing</h2>
<table><tr><th>Free trial</th><td>30 days, with adverts</td></tr>
<tr><th>Subscription</th><td>£4.99 per month for each user or each device (your organisation chooses). Subscribers see 95% fewer adverts.</td></tr></table>

<h2>Downloads</h2>
<div class="grid">{dl}</div>

<h2>System requirements (planned)</h2>
<p>Windows 11 first, then macOS and Linux as each platform passes testing. The management console runs in current Chrome, Edge, Firefox and Safari, and as an installable app.</p>

<footer><p><a href="{BASE}privacy.html">Privacy</a>&nbsp;&nbsp; <a href="mailto:support@softwareequality.com">Support</a></p><p>Licence: proprietary, © Equality Software Ltd, registered in England, Co. No. 15006381.</p></footer>
</main>"""


def privacy_body():
    src = (P / "web" / "app" / "privacy" / "page.tsx").read_text()
    parts = src.split("<StaticPage title=\"Privacy\">", 1)[1].split("</StaticPage>", 1)[0]
    parts = parts.replace("<p>Equality Software Ltd operates Agentic Antivirus. This page describes what the service collects. It must be reviewed by the product owner before publication.</p>",
                          "<p>Equality Software Ltd operates Agentic Antivirus. This page describes what the service collects.</p>")
    return f'<main><header><a href="{BASE}"><strong>Agentic Antivirus</strong></a></header><h1>Privacy</h1>{parts}</main>'


def page(title, body, desc):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="icon" href="{BASE}icon.svg" type="image/svg+xml"><link rel="canonical" href="{SITE}{BASE}">
<style>{CSS}</style></head><body class="aav">{body}</body></html>"""


def main():
    m = json.loads((HERE / "releases.json").read_text())
    if OUT.exists():
        shutil.rmtree(OUT)
    static = OUT / "static" / "apps" / "agentic-antivirus"
    static.mkdir(parents=True)
    desc = "Antivirus, behaviour detection and AI-assisted incident response with human approval. Early access."
    (static / "index.html").write_text(page("Agentic Antivirus | Equality Software", product_body(m), desc))
    (static / "privacy.html").write_text(page("Privacy | Agentic Antivirus", privacy_body(), "Privacy notice for Agentic Antivirus."))
    shutil.copy(P / "web" / "public" / "icons" / "icon.svg", static / "icon.svg")
    wp = OUT / "wordpress"
    wp.mkdir()
    (wp / "agentic-antivirus-block.html").write_text(f'<style>{CSS}</style><div class="aav">{product_body(m)}</div>')
    zpath = OUT / "agentic-antivirus-website.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (OUT / "static").rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(OUT / "static"))
    print(zpath, [str(p.relative_to(OUT)) for p in OUT.rglob("*") if p.is_file()])


if __name__ == "__main__":
    main()
