"""Accessibility gate (UI-07, DEL-02): runs axe-core (WCAG 2.0/2.1/2.2 A and AA rules) in Chromium
against every console route, in light, dark, high-contrast and RTL. Fails on serious/critical issues.
Usage: python a11y_check.py BASE_URL AXE_JS [TOKEN TENANT]"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

ROUTES = ["/", "/?assistant", "/approvals/", "/response/", "/incidents/", "/alerts/", "/security/", "/devices/", "/quarantine/", "/policies/", "/ddos/",
          "/integrations/", "/files/", "/settings/", "/billing/", "/audit/", "/help/", "/privacy/", "/login/",
          "/register/", "/forgot/", "/reset-password/", "/verify-email/", "/accept-invite/"]
VARIANTS = [("light", "en"), ("dark", "en"), ("high_contrast", "en"), ("light", "ar")]
# L10N-10: AAV_A11Y_ALL_LOCALES=1 adds every catalogue locale (light theme) on the routes with the most text,
# and checks that <html> carries the locale's lang and direction.
LOCALE_ROUTES = ["/", "/devices/", "/settings/", "/privacy/", "/login/", "/help/"]
if os.getenv("AAV_A11Y_ALL_LOCALES") == "1":
    import pathlib
    import re as _re
    _src = (pathlib.Path(__file__).resolve().parents[1] / "lib" / "i18n.tsx").read_text(encoding="utf-8")
    _locs = _re.findall(r'"([a-z]{2,3}(?:-[A-Za-z]+)?)"', _src.split("export const LOCALES = [")[1].split("]")[0])
    VARIANTS += [("light", loc) for loc in _locs if loc not in ("en", "ar")]
RTL = {"ar", "fa", "he", "ps", "ur", "yi"}


def main(base, axe_path, token="", tenant=""):
    axe = open(axe_path, encoding="utf-8").read()
    failures, checked = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        for theme, locale in VARIANTS:
            ctx = b.new_context()
            ctx.add_init_script(f"sessionStorage.setItem('aav.token',{json.dumps(token)});"
                                f"sessionStorage.setItem('aav.tenant',{json.dumps(tenant)});"
                                f"localStorage.setItem('aav.theme','{theme}');localStorage.setItem('aav.locale','{locale}');")
            routes = ROUTES if (theme, locale) in VARIANTS[:4] else LOCALE_ROUTES
            for route in routes:
                pg = ctx.new_page()
                pg.goto(base + route.replace("?assistant", ""), wait_until="networkidle")
                pg.wait_for_timeout(300)
                if route.endswith("?assistant"):   # the assistant drawer open, with its attachment controls
                    pg.click("button.assistant-fab")
                    pg.wait_for_timeout(200)
                lang, dirn = pg.evaluate("() => [document.documentElement.lang, document.documentElement.dir]")
                if lang != locale or (dirn == "rtl") != (locale in RTL):
                    failures.append({"route": route, "theme": theme, "locale": locale, "rule": "aav-lang-dir",
                                     "impact": "serious", "nodes": [f"html lang={lang!r} dir={dirn!r}"]})
                pg.add_script_tag(content=axe)
                res = pg.evaluate("""() => axe.run(document, {runOnly: {type: 'tag',
                    values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})""")
                checked += 1
                for v in res["violations"]:
                    if v["impact"] in ("serious", "critical"):
                        failures.append({"route": route, "theme": theme, "locale": locale, "rule": v["id"],
                                         "impact": v["impact"], "nodes": [n["target"] for n in v["nodes"][:3]]})
                pg.close()
            ctx.close()
        b.close()
    print(json.dumps({"pages_checked": checked, "serious_or_critical": failures}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
