"""Native-speaker review of a locale (L10N-11, L10N-12).

1. Export a review sheet (opens in Excel / Google Sheets / LibreOffice):
       python tools/i18n_review.py export fr            -> review/fr.csv
   Columns: key, english, translation, approved, correction, comment.
2. The reviewer writes "yes" in approved for every correct line, or puts the fixed text in correction (which counts
   as approved). Lines left blank stay unreviewed.
3. Import it:
       python tools/i18n_review.py import review/fr.csv --reviewer "Name <email>"
   Corrections replace the text (placeholders must still match English), approved keys go into _meta.reviewed_keys,
   and once every key is reviewed the locale's origin becomes "human" and the console stops showing the machine
   translation notice. Re-running the translator never overwrites reviewed keys.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
I18N = HERE.parent / "shared" / "i18n"
PH = re.compile(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,}]")


def _load(locale: str) -> tuple[dict, dict, dict]:
    base = {k: v for k, v in json.loads((I18N / "en.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    data = json.loads((I18N / f"{locale}.json").read_text(encoding="utf-8"))
    meta = data.get("_meta", {}) if isinstance(data.get("_meta"), dict) else {}
    return base, {k: v for k, v in data.items() if not k.startswith("_")}, meta


def export(locale: str, out_dir: Path) -> Path:
    base, msgs, meta = _load(locale)
    reviewed = set(meta.get("reviewed_keys", []))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{locale}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["key", "english", "translation", "approved", "correction", "comment"])
        for k, en in base.items():
            w.writerow([k, en, msgs.get(k, ""), "yes" if k in reviewed else "", "", ""])
    return path


def import_sheet(sheet: Path, reviewer: str) -> dict:
    locale = sheet.stem
    base, msgs, meta = _load(locale)
    reviewed = set(meta.get("reviewed_keys", []))
    hashes = meta.get("source_hashes", {})
    rejected, approved, corrected = [], 0, 0
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            k = row.get("key", "")
            if k not in base:
                continue
            fix = (row.get("correction") or "").strip()
            if fix:
                if sorted(set(PH.findall(fix))) != sorted(set(PH.findall(base[k]))):
                    rejected.append(f"{k}: placeholders must stay {sorted(set(PH.findall(base[k])))}")
                    continue
                msgs[k] = fix
                corrected += 1
                reviewed.add(k)
            elif (row.get("approved") or "").strip().lower() in ("yes", "y", "ok", "x", "true", "1") and msgs.get(k):
                approved += 1
                reviewed.add(k)
    import hashlib
    for k in reviewed:
        hashes[k] = hashlib.sha256(base[k].encode()).hexdigest()[:16]
    meta.update(reviewed_keys=sorted(reviewed & set(msgs)), source_hashes=hashes,
                reviewers=sorted(set(meta.get("reviewers", [])) | {reviewer}),
                reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if set(base) <= reviewed:
        meta["origin"] = "human"
        meta["label"] = "reviewed by a native speaker"
    (I18N / f"{locale}.json").write_text(json.dumps({"_meta": meta, **dict(sorted(msgs.items()))}, ensure_ascii=False,
                                                    indent=2) + "\n", encoding="utf-8")
    return {"locale": locale, "approved": approved, "corrected": corrected, "rejected": rejected,
            "reviewed": len(meta["reviewed_keys"]), "total": len(base), "origin": meta.get("origin")}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("locale")
    e.add_argument("--out", default="review")
    i = sub.add_parser("import")
    i.add_argument("sheet")
    i.add_argument("--reviewer", required=True)
    a = ap.parse_args()
    if a.cmd == "export":
        print(export(a.locale, Path(a.out)))
    else:
        r = import_sheet(Path(a.sheet), a.reviewer)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 1 if r["rejected"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
