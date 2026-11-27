"""Machine-translate shared/i18n/en.json into the 100-locale catalogue (L10N-01, L10N-11, L10N-12).

Engines, in order (the first available one is used for a locale):
  file     pre-translated units from shared/i18n/units/<locale>.tsv ("index<TAB>text" lines over the unit list
           in shared/i18n/units/units.json; produced by an assistant or a translation vendor). --engine file
  claude   Anthropic Messages API, when ANTHROPIC_API_KEY is set (paid; best quality and coverage)
  m2m100   facebook/m2m100_418M (MIT licence), local CPU inference, 100 languages
  madlad   google/madlad400-3b-mt (Apache-2.0), local CPU inference, for locales M2M100 lacks
Each result keeps the source's {placeholders} and ICU plural branches; a string whose placeholders do
not survive is dropped (the console then shows English for that key, never a broken message).
Output files carry "_meta": origin machine:catalogue, engine, source hash, and reviewed_keys (filled
when a native reviewer approves keys). Human-reviewed keys in an existing file are never overwritten.

usage: python tools/i18n_translate.py --locales fr,de [--engine auto|claude|m2m100|madlad] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
I18N = HERE.parent / "shared" / "i18n"
sys.path.insert(0, str(HERE.parent / "control-plane"))
from app.i18n import LOCALES  # noqa: E402

PH = re.compile(r"\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}")
PLURAL = re.compile(r"^\{(\w+), plural, (.*)\}$", re.S)
BRANCH = re.compile(r"(=?\w+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
NAME = {"zh-Hans": "Simplified Chinese", "fil": "Filipino", "ceb": "Cebuano", "hmn": "Hmong", "bho": "Bhojpuri",
        "mai": "Maithili", "sat": "Santali", "jv": "Javanese", "su": "Sundanese"}
M2M = {"zh-Hans": "zh", "fil": "tl", "he": "he", "no": "no"}
M2M_SUPPORTED = set("af am ar ast az ba be bg bn br bs ca ceb cs cy da de el en es et fa ff fi fr fy ga gd gl gu ha he "
                    "hi hr ht hu hy id ig ilo is it ja jv ka kk km kn ko lb lg ln lo lt lv mg mk ml mn mr ms my ne nl no "
                    "ns oc or pa pl ps pt ro ru sd si sk sl so sq sr ss su sv sw ta th tl tn tr uk ur uz vi wo xh yi yo "
                    "zh zu".split())
MADLAD = {"zh-Hans": "zh", "fil": "fil", "he": "iw", "no": "no"}


def src_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def placeholders(s: str) -> list[str]:
    return sorted(set(re.sub(r"\s", "", p) for p in PH.findall(s)))


def _plural_span(msg: str):
    """(start, end, var, branches) of the first ICU plural block, found by brace matching."""
    m = re.search(r"\{(\w+),\s*plural,", msg)
    if not m:
        return None
    depth, i = 0, m.start()
    while i < len(msg):
        depth += {"{": 1, "}": -1}.get(msg[i], 0)
        if depth == 0:
            break
        i += 1
    body = msg[m.end():i]
    return m.start(), i + 1, m.group(1), BRANCH.findall(body)


def split_units(msg: str) -> tuple[list[str], callable]:
    """Translatable units of one ICU message (text around a plural block and each plural branch) and a
    function that rebuilds the message from translated units."""
    span = _plural_span(msg)
    if not span:
        return [msg], lambda xs: xs[0]
    a, b, var, branches = span
    pre, post = msg[:a], msg[b:]
    units = ([pre] if pre.strip() else []) + [t for _, t in branches] + ([post] if post.strip() else [])

    def build(xs):
        xs = list(xs)
        p = xs.pop(0) if pre.strip() else pre
        q = xs.pop() if post.strip() else post
        sep_p = " " if pre.strip() and pre.endswith(" ") and not p.endswith(" ") else ""
        sep_q = " " if post.strip() and post.startswith(" ") and not q.startswith(" ") else ""
        block = "{" + var + ", plural, " + " ".join(f"{sel} {{{x}}}" for (sel, _), x in zip(branches, xs)) + "}"
        return f"{p}{sep_p}{block}{sep_q}{q}"
    return units, build


def mask(text: str) -> tuple[str, list[str]]:
    found = PH.findall(text) + (["#"] if "#" in text else [])
    out = text
    for i, p in enumerate(found):
        out = out.replace(p, f"[{i}]", 1)
    return out, found


def unmask(text: str, found: list[str]) -> str:
    for i, p in enumerate(found):
        text = re.sub(rf"\[\s*{i}\s*\]", lambda _: p, text, count=1)
    return text


class Claude:
    name = "claude"

    def __init__(self):
        import httpx
        self.http = httpx.Client(base_url="https://api.anthropic.com", timeout=120)
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def translate(self, texts: list[str], locale: str) -> list[str]:
        lang = NAME.get(locale, locale)
        out: list[str] = []
        for i in range(0, len(texts), 80):
            chunk = {str(j): t for j, t in enumerate(texts[i:i + 80])}
            r = self.http.post("/v1/messages", headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"],
                                                        "anthropic-version": "2023-06-01"}, json={
                "model": self.model, "max_tokens": 8000,
                "system": f"Translate UI strings of a security product from English to {lang} (BCP 47 '{locale}'). "
                          "Keep [0], [1] markers exactly. Keep product names. Reply with JSON only, same keys.",
                "messages": [{"role": "user", "content": json.dumps(chunk, ensure_ascii=False)}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json()["content"])
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
            out.extend(data.get(str(j), "") for j in range(len(chunk)))
        return out


class HF:
    def __init__(self, model_id: str, codes: dict, madlad: bool):
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        self.name = model_id
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_id)
        self.codes, self.madlad = codes, madlad

    def translate(self, texts: list[str], locale: str) -> list[str]:
        import torch
        code = self.codes.get(locale, locale)
        out: list[str] = []
        for i in range(0, len(texts), 16):
            batch = texts[i:i + 16]
            if self.madlad:
                enc = self.tok([f"<2{code}> {t}" for t in batch], return_tensors="pt", padding=True, truncation=True)
                kw = {}
            else:
                self.tok.src_lang = "en"
                enc = self.tok(batch, return_tensors="pt", padding=True, truncation=True)
                kw = {"forced_bos_token_id": self.tok.get_lang_id(code)}
            with torch.no_grad():
                gen = self.model.generate(**enc, max_new_tokens=256, num_beams=2, **kw)
            out.extend(self.tok.batch_decode(gen, skip_special_tokens=True))
        return out


UNITS_DIR = I18N / "units"
# Units kept verbatim in every language (product, vendor and protocol names, identifiers, addresses).
KEEP = {"Claude", "Agentic Antivirus", "action.approve", "CIDR", "SHA-256", "privacy@softwareequality.com",
        "support@softwareequality.com", "shop.example.com"}


def all_units() -> list[str]:
    """Every masked translatable unit of en.json, de-duplicated, in catalogue order."""
    base = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    units: list[str] = []
    for v in base.values():
        for part in split_units(v)[0]:
            units.append(mask(part)[0])
    return list(dict.fromkeys(units))


class FileEngine:
    name = "file"

    def __init__(self):
        self.units = json.loads((UNITS_DIR / "units.json").read_text(encoding="utf-8"))
        if self.units != all_units():
            raise SystemExit("shared/i18n/units/units.json is out of date: run tools/i18n_translate.py --export-units")
        self.index = {u: i for i, u in enumerate(self.units)}

    def table(self, locale: str) -> dict[int, str]:
        f = UNITS_DIR / f"{locale}.tsv"
        out: dict[int, str] = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            if "\t" in line:
                i, _, text = line.partition("\t")
                if i.strip().isdigit():
                    out[int(i)] = text.replace("\\n", "\n")
        return out

    def translate(self, texts: list[str], locale: str) -> list[str]:
        t = self.table(locale)
        out = []
        for x in texts:
            i = self.index.get(x)
            out.append(x if x in KEEP else (t.get(i, "") if i is not None else ""))
        return out


def engine_for(locale: str, choice: str, cache: dict):
    if choice == "file" or (choice == "auto" and (UNITS_DIR / f"{locale}.tsv").exists()):
        return cache.setdefault("file", FileEngine())
    if choice in ("auto", "claude") and os.getenv("ANTHROPIC_API_KEY"):
        return cache.setdefault("claude", Claude())
    if choice == "claude":
        raise SystemExit("ANTHROPIC_API_KEY is not set")
    if choice in ("auto", "m2m100") and M2M.get(locale, locale) in M2M_SUPPORTED:
        if "m2m" not in cache:
            cache["m2m"] = HF("facebook/m2m100_418M", M2M, madlad=False)
        return cache["m2m"]
    if choice in ("auto", "madlad"):
        if "madlad" not in cache:
            cache["madlad"] = HF("google/madlad400-3b-mt", MADLAD, madlad=True)
        return cache["madlad"]
    return None


def translate_locale(locale: str, choice: str, cache: dict, limit: int | None) -> dict:
    base = json.loads((I18N / "en.json").read_text(encoding="utf-8"))
    path = I18N / f"{locale}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    meta = old.get("_meta", {}) if isinstance(old.get("_meta"), dict) else {}
    human = set(meta.get("reviewed_keys", [])) if meta.get("origin", "human") != "human" else \
        {k for k in old if not k.startswith("_")}
    hashes = meta.get("source_hashes", {})
    todo = [k for k, v in base.items() if k not in human and (k not in old or hashes.get(k) != src_hash(v))][:limit]
    eng = engine_for(locale, choice, cache)
    if eng is None:
        return {"locale": locale, "skipped": "no engine"}
    units, rebuild, masks = [], [], []
    for k in todo:
        parts, build = split_units(base[k])
        idx = []
        for p in parts:
            masked, found = mask(p)
            idx.append(len(units))
            units.append(masked)
            masks.append(found)
        rebuild.append((k, idx, build))
    t0 = time.time()
    translated = eng.translate(units, locale) if units else []
    out = {k: v for k, v in old.items() if not k.startswith("_") and k in base}
    ok = dropped = 0
    for k, idx, build in rebuild:
        try:
            text = build([unmask(translated[i], masks[i]) for i in idx]).strip()
        except (IndexError, TypeError):
            text = ""
        if text and placeholders(text) == placeholders(base[k]) and ("#" in text) == ("#" in base[k]):
            out[k] = text
            hashes[k] = src_hash(base[k])
            ok += 1
        else:
            out.pop(k, None)
            dropped += 1
    meta = {"origin": "human" if not out else "machine:catalogue", "engine": eng.name,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reviewed_keys": sorted(human & set(out)), "source_hashes": {k: hashes[k] for k in out if k in hashes},
            "label": "machine translated, not yet reviewed"}
    path.write_text(json.dumps({"_meta": meta, **dict(sorted(out.items()))}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return {"locale": locale, "engine": eng.name, "translated": ok, "dropped_placeholder_mismatch": dropped,
            "keys_total": len(base), "keys_present": len(out), "seconds": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locales", default="all")
    ap.add_argument("--engine", default="auto", choices=["auto", "file", "claude", "m2m100", "madlad"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--export-units", action="store_true", help="write shared/i18n/units/units.json and units.tsv")
    a = ap.parse_args()
    if a.export_units:
        UNITS_DIR.mkdir(exist_ok=True)
        u = all_units()
        (UNITS_DIR / "units.json").write_text(json.dumps(u, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        (UNITS_DIR / "units.tsv").write_text("".join(f"{i}\t{x}\n" for i, x in enumerate(u)), encoding="utf-8")
        print(f"{len(u)} units")
        return
    locales = [x for x in LOCALES if x != "en"] if a.locales == "all" else a.locales.split(",")
    cache: dict = {}
    report = [translate_locale(loc, a.engine, cache, a.limit) for loc in locales]
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
