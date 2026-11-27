"""Record product-owner decisions in the Release 1 evidence register (RA-14/RA-15).

Usage:
    python tools/record_decisions.py --owner "Ali" --date 2026-11-27 --accept-all-proposed

Every item whose disposition is "Accept proposed decision" is marked passed at
verification level "owner-decided", with the proposal text as the decision. The
product-owner items (D-02, PRJ-13, PRJ-14) are recorded with the named owner.
The script is idempotent and never touches items that are already passed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "evidence" / "evidence-r1.json"

OWNER_ITEMS = {"D-02", "PRJ-13", "PRJ-14"}


def apply(data: dict, owner: str, date: str, accept_all: bool) -> list[str]:
    changed: list[str] = []
    for item in data["items"]:
        if item["status"] == "passed":
            continue
        rid = item["requirement_id"]
        if rid in OWNER_ITEMS:
            item.update(
                status="passed",
                verification_level="owner-decided",
                evidence=f"{owner} named product owner and release approval owner ({date})",
                owner=owner,
                verified_at=date,
            )
            changed.append(rid)
        elif accept_all and item["disposition"] == "Accept proposed decision":
            item.update(
                status="passed",
                verification_level="owner-decided",
                evidence=f"Proposed decision accepted by {owner} ({date}): {item.get('note') or item['evidence']}",
                owner=owner,
                verified_at=date,
            )
            changed.append(rid)
    data["decisions_recorded"] = {"owner": owner, "date": date, "items": sorted(set(
        data.get("decisions_recorded", {}).get("items", []) + changed))}
    if "owner-decided" not in data["status_values"]:
        data.setdefault("verification_levels_added", []).append("owner-decided")
    return changed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--accept-all-proposed", action="store_true")
    ap.add_argument("--register", default=str(REGISTER))
    a = ap.parse_args()
    path = Path(a.register)
    data = json.loads(path.read_text())
    changed = apply(data, a.owner, a.date, a.accept_all_proposed)
    path.write_text(json.dumps(data, indent=1) + "\n")
    print(f"recorded {len(changed)} decisions: {', '.join(changed)}")


if __name__ == "__main__":
    main()
