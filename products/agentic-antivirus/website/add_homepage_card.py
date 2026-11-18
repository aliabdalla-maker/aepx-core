"""Updates the "Products we have built ourselves" section of the live softwareequality.com homepage
(index.html): adds the Agentic Antivirus card after the Agentic IDE card, and replaces the generic line
icons of AEP-X, Good Hours, Business AI Manager and SIM2eSIM with their product icons (same 48 px image
mark the Agentic IDE card uses). Idempotent; fails if the section's layout has changed.
Usage: python add_homepage_card.py index.html  (writes index.html in place; keeps index.html.bak)"""
import re
import shutil
import sys
from pathlib import Path

ANCHOR = '<span class="se-product-link">See the Agentic IDE &rarr;</span>\n      </a>\n'
CARD = '''      <a class="se-product reveal" href="/apps/agentic-antivirus/">
        <div class="se-product-top"><div class="se-product-mark" style="padding:0;overflow:hidden"><img src="/agentic-antivirus-icon.png" alt="" width="48" height="48" style="width:100%;height:100%;object-fit:cover"></div><div><h3>Agentic Antivirus</h3><div class="se-product-kind">Endpoint protection, EDR and DDoS monitoring with governed AI</div></div></div>
        <p>Scans and quarantines malware, catches ransomware and credential-theft behaviour, and explains each incident with evidence. The AI suggests responses; your team approves every action. Early access: 30 days free, then &pound;4.99 a month per user or device.</p>
        <div class="se-product-tags"><span>Python</span><span>FastAPI</span><span>PostgreSQL</span><span>Early access</span></div>
        <span class="se-product-link">See Agentic Antivirus &rarr;</span>
      </a>
'''


ICONS = {  # card href -> icon file served from the site root
    "/case-study-aepx": "/aepx-icon.png",
    "/case-study-good-hours": "/good-hours-icon.png",
    "/case-study-business-ai-manager": "/business-ai-manager-icon.png",
    "https://sim2esim.softwareequality.com/": "/sim2esim-icon.png",
}
IMG_MARK = ('<div class="se-product-mark" style="padding:0;overflow:hidden"><img src="{src}" alt="" width="48" '
            'height="48" style="width:100%;height:100%;object-fit:cover"></div>')


def swap_icons(html: str) -> str:
    for href, src in ICONS.items():
        pat = re.compile(r'(<a class="se-product[^"]*" href="' + re.escape(href) + r'"[^>]*>\s*<div class="se-product-top">)'
                         r'<div class="se-product-mark">\s*<svg.*?</svg>\s*</div>', re.S)
        html, n = pat.subn(lambda m: m.group(1) + IMG_MARK.format(src=src), html, count=1)
        if n == 0 and f'src="{src}"' not in html:
            raise SystemExit(f"card {href} not found; homepage layout changed")
    return html


def add(html: str) -> str:
    html = swap_icons(html)
    if 'href="/apps/agentic-antivirus/"' in html:
        return html
    if html.count(ANCHOR) != 1:
        raise SystemExit("could not find the Agentic IDE card exactly once; homepage layout changed")
    return html.replace(ANCHOR, ANCHOR + CARD)


if __name__ == "__main__":
    p = Path(sys.argv[1])
    shutil.copy(p, p.with_suffix(p.suffix + ".bak"))
    p.write_text(add(p.read_text(encoding="utf-8")), encoding="utf-8")
    print("card present")
