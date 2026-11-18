"""Locale catalogue (L10N-01..13). The 100 codes are exactly the v3 template catalogue.
Coverage is measured from the shared message catalogues; nothing is reported as translated
unless every key exists in that locale's file (L10N-11/12)."""
from __future__ import annotations

import json
import os
from pathlib import Path

LOCALES = ["en", "es", "zh-Hans", "hi", "ar", "fr", "pt", "ru", "bn", "id", "ur", "de", "ja", "sw", "mr", "te", "tr",
           "ta", "vi", "ko", "it", "th", "gu", "fa", "pl", "uk", "pa", "ml", "jv", "nl", "ro", "hu", "el", "cs", "sv",
           "fi", "he", "da", "no", "sk", "bg", "sr", "hr", "lt", "lv", "et", "sl", "ca", "eu", "gl", "af", "am", "az",
           "be", "bs", "cy", "eo", "fil", "ha", "hy", "ig", "is", "ka", "kk", "km", "kn", "ku", "ky", "lo", "mk", "mn",
           "my", "ne", "or", "ps", "si", "sq", "su", "tg", "tk", "tl", "uz", "yo", "zu", "xh", "so", "rw", "mg", "ny",
           "sn", "st", "tn", "ts", "wo", "yi", "ceb", "hmn", "bho", "mai", "sat"]
assert len(LOCALES) == 100 and len(set(LOCALES)) == 100

RTL = {"ar", "fa", "he", "ps", "ur", "yi"}
FALLBACK = "en"

MESSAGES_DIR = Path(os.getenv("AAV_MESSAGES_DIR", Path(__file__).resolve().parents[2] / "shared" / "i18n"))


def fallback_chain(locale: str) -> list[str]:
    chain = [locale]
    if "-" in locale:
        chain.append(locale.split("-")[0])
    if FALLBACK not in chain:
        chain.append(FALLBACK)
    return chain


def coverage() -> list[dict]:
    base_file = MESSAGES_DIR / f"{FALLBACK}.json"
    base = json.loads(base_file.read_text(encoding="utf-8")) if base_file.exists() else {}
    keys = set(base)
    out = []
    for loc in LOCALES:
        f = MESSAGES_DIR / f"{loc}.json"
        msgs = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        present = keys & {k for k, v in msgs.items() if isinstance(v, str) and v.strip()}
        pct = round(100 * len(present) / len(keys), 1) if keys else 0.0
        out.append({"locale": loc, "direction": "rtl" if loc in RTL else "ltr", "keys_total": len(keys),
                    "keys_translated": len(present), "coverage_pct": pct,
                    "status": "complete" if keys and present == keys else ("partial" if present else "unavailable"),
                    "fallback_chain": fallback_chain(loc)})
    return out
