"""Automated translation QA for every catalogue locale (L10N-11, L10N-12). Run after any translation change:

    python tools/i18n_qa.py            # writes docs/matrices/translation-qa.md, exits 1 on hard failures

Hard failures (the string would break the console): placeholder set differs from English, an ICU plural block lost,
unbalanced braces. Warnings (a native reviewer should look first): text in the wrong writing system, text left
identical to English, length far outside the usual ratio. Machine output stays labelled "not yet reviewed" in the
console until tools/i18n_review.py imports a native speaker's approval.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
I18N = HERE.parent / "shared" / "i18n"
OUT = HERE.parent / "docs" / "matrices" / "translation-qa.md"
sys.path.insert(0, str(HERE.parent / "control-plane"))
from app.i18n import LOCALES, RTL  # noqa: E402

PH = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,}]")
KEEP_KEYS_PREFIX = ()
# Unicode script name fragments expected for the letters of each locale (unicodedata.name prefixes).
SCRIPT = {"zh-Hans": ("CJK",), "ja": ("CJK", "HIRAGANA", "KATAKANA"), "ko": ("HANGUL",), "ar": ("ARABIC",),
          "fa": ("ARABIC",), "ur": ("ARABIC",), "ps": ("ARABIC",), "ku": ("LATIN",), "he": ("HEBREW",),
          "yi": ("HEBREW",), "hi": ("DEVANAGARI",), "mr": ("DEVANAGARI",), "ne": ("DEVANAGARI",),
          "bho": ("DEVANAGARI",), "mai": ("DEVANAGARI",), "bn": ("BENGALI",), "pa": ("GURMUKHI",),
          "gu": ("GUJARATI",), "or": ("ORIYA",), "ta": ("TAMIL",), "te": ("TELUGU",), "kn": ("KANNADA",),
          "ml": ("MALAYALAM",), "si": ("SINHALA",), "th": ("THAI",), "lo": ("LAO",), "my": ("MYANMAR",),
          "km": ("KHMER",), "ka": ("GEORGIAN",), "hy": ("ARMENIAN",), "am": ("ETHIOPIC",), "sat": ("OL CHIKI",),
          "el": ("GREEK",), "ru": ("CYRILLIC",), "uk": ("CYRILLIC",), "bg": ("CYRILLIC",), "be": ("CYRILLIC",),
          "mk": ("CYRILLIC",), "sr": ("CYRILLIC",), "kk": ("CYRILLIC",), "ky": ("CYRILLIC",), "mn": ("CYRILLIC",),
          "tg": ("CYRILLIC",)}
VERBATIM_OK = {"Claude", "Agentic Antivirus", "action.approve", "CIDR", "SHA-256", "privacy@softwareequality.com",
               "support@softwareequality.com", "shop.example.com", "Google", "N/A", "IP", "DNS", "DDoS", "MB", "OK"}


def letters_in_script(text: str, scripts: tuple[str, ...]) -> float:
    text = re.sub(r"\{[^{}]*\}|https?://\S+|\b[A-Z][A-Za-z0-9.-]*\b", "", text)   # placeholders, URLs, names
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    ok = sum(1 for c in letters if unicodedata.name(c, "").startswith(scripts))
    return ok / len(letters)


def check_locale(loc: str, base: dict) -> dict:
    f = I18N / f"{loc}.json"
    if not f.exists():
        return {"locale": loc, "status": "missing", "keys": 0, "errors": [], "warnings": [],
                "direction": "rtl" if loc in RTL else "ltr"}
    data = json.loads(f.read_text(encoding="utf-8"))
    meta = data.get("_meta", {}) if isinstance(data.get("_meta"), dict) else {}
    msgs = {k: v for k, v in data.items() if not k.startswith("_")}
    errors, warnings = [], []
    same = wrong_script = long = 0
    for k, en in base.items():
        t = msgs.get(k)
        if not isinstance(t, str) or not t.strip():
            continue
        if sorted(set(PH.findall(t))) != sorted(set(PH.findall(en))):
            errors.append(f"{k}: placeholders {sorted(set(PH.findall(t)))} != {sorted(set(PH.findall(en)))}")
        if ("plural," in en) != ("plural," in t):
            errors.append(f"{k}: ICU plural block lost or added")
        if t.count("{") != t.count("}"):
            errors.append(f"{k}: unbalanced braces")
        if t == en and en not in VERBATIM_OK and len(en) > 3 and loc != "en":
            same += 1
        if loc in SCRIPT and letters_in_script(t, SCRIPT[loc]) < 0.6:
            wrong_script += 1
        if len(en) >= 12 and not (0.25 <= len(t) / len(en) <= 3.5):
            long += 1
    present = sum(1 for k in base if isinstance(msgs.get(k), str) and msgs[k].strip())
    if same > max(10, 0.05 * present):
        warnings.append(f"{same} strings identical to English")
    if wrong_script:
        warnings.append(f"{wrong_script} strings mostly outside the expected script ({'/'.join(SCRIPT[loc])})")
    if long:
        warnings.append(f"{long} strings with an unusual length ratio")
    reviewed = len(meta.get("reviewed_keys", [])) if meta.get("origin") != "human" else present
    return {"locale": loc, "status": "complete" if present == len(base) else "partial", "keys": present,
            "origin": meta.get("origin", "human"), "engine": meta.get("engine", ""), "reviewed": reviewed,
            "errors": errors, "warnings": warnings, "direction": "rtl" if loc in RTL else "ltr"}


def main() -> int:
    base = {k: v for k, v in json.loads((I18N / "en.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    rows = [check_locale(loc, base) for loc in LOCALES if loc != "en"]
    hard = [r for r in rows if r["errors"]]
    lines = [f"| {r['locale']} | {r['direction']} | {r['keys']}/{len(base)} | {r.get('origin', '—')} | "
             f"{r.get('reviewed', 0)}/{len(base)} | {len(r['errors'])} | {'; '.join(r['warnings']) or '—'} |" for r in rows]
    done = sum(r["keys"] == len(base) for r in rows)
    OUT.write_text(
        "# Translation QA\n\nGenerated by `tools/i18n_qa.py`. Hard errors block a locale (placeholders, plural blocks, "
        "braces). Warnings point a native reviewer at likely problems. **Reviewed** counts keys a native speaker "
        f"approved through `tools/i18n_review.py`; until then the console labels the text machine translated.\n\n"
        f"Locales with every key: {done} of {len(rows)} (plus English). Locales with hard errors: {len(hard)}.\n\n"
        "| Locale | Dir | Keys | Origin | Reviewed | Errors | Warnings |\n|---|---|---|---|---|---|---|\n"
        + "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"complete": done, "with_errors": [r["locale"] for r in hard],
                      "errors": {r["locale"]: r["errors"][:5] for r in hard}}, ensure_ascii=False, indent=1))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
