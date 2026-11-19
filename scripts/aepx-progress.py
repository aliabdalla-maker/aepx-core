#!/usr/bin/env python3
"""Render planning estimates with explicit evidence and verification limitations."""
import argparse
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    data = json.loads(Path("docs/AEPX-Milestones.json").read_text())
    milestones = data["milestones"]
    ids = [m["id"] for m in milestones]
    assert len(ids) == len(set(ids)), "Duplicate milestone IDs"
    assert milestones, "Milestones must not be empty"
    for m in milestones:
        assert isinstance(m["completion"], int) and 0 <= m["completion"] <= 100
        assert m.get("evidence"), "Every milestone requires evidence"
    avg = round(sum(m["completion"] for m in milestones) / len(milestones))
    assert avg == data["overall_estimate_percent"], (
        f"Stale overall estimate: expected {avg}, found {data['overall_estimate_percent']}"
    )
    if args.validate:
        print(f"PASS: {len(milestones)} milestones; illustrative overall {avg}%")
        return
    rows = ["# AEP-X milestone progress", "",
            "**Percentages are planning estimates, not release acceptance evidence.**", "",
            f"Illustrative overall estimate: **{avg}%**", "",
            "| ID | Milestone | Estimate | Status | Evidence |",
            "|---|---|---:|---|---|"]
    for m in milestones:
        evidence = m["evidence"].replace("|", "/").replace("\n", " ")
        rows.append(f'| {m["id"]} | {m["name"]} | {m["completion"]}% | {m["status"]} | {evidence} |')
    rows.extend(["", "**Production readiness: not established.**",
                 "CI checks do not prove private Codespace, full backend, MCP, RAG or OCI deployment health."])
    output = "\n".join(rows) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output)
        print(f"Wrote {path}")
    else:
        print(output)

if __name__ == "__main__":
    main()
