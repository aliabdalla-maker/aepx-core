"""Adds the Agentic Antivirus card to the "Products we have built ourselves" section of the live
softwareequality.com homepage (index.html), right after the Agentic IDE card. Idempotent.
Usage: python add_homepage_card.py index.html  (writes index.html in place; keeps index.html.bak)"""
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


def add(html: str) -> str:
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
