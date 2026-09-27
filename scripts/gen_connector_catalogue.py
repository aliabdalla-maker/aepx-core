"""Regenerate docs/Connector-Catalogue.md from connectors/catalogue.json.

catalogue.json is the single source of truth; the Markdown catalogue is a
generated view of it and must not be hand-edited.

    python scripts/gen_connector_catalogue.py          # rewrite the doc
    python scripts/gen_connector_catalogue.py --check  # exit 1 if the doc is stale
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "connectors" / "catalogue.json"
DOC = ROOT / "docs" / "Connector-Catalogue.md"


def render(catalogue: dict) -> str:
    connectors = catalogue["connectors"]
    categories: dict[str, list[dict]] = {}
    for c in connectors:  # keep catalogue order for both categories and rows
        categories.setdefault(c["category"], []).append(c)

    out = [
        f"# AEP-X Connector Catalogue — {len(connectors)} Connectors",
        "",
        "**Generated from** `connectors/catalogue.json` (single source of truth — regenerate this file rather than editing it).",
        "**Architecture:** one coarse-grained service per category, one adapter per connector "
        "([SOA-Architecture.md](SOA-Architecture.md) §3.1). `specialized` = working adapter with a concrete "
        "implementation path; `stub` = catalogued, routed, governed, returning canonical stub responses until a "
        "real integration lands.",
        "",
        f"**Total: {len(connectors)} connectors across {len(categories)} categories.**",
    ]
    for category, rows in categories.items():
        out += [
            "",
            f"## {category} ({len(rows)})",
            "",
            "| Connector | Protocols | AIA risk | Min trust | Maturity |",
            "|---|---|---|---|---|",
        ]
        for c in rows:
            out.append(
                f"| {c['name']} | {', '.join(c['protocols'])} | {c['ai_risk_class']} | "
                f"{c['min_trust_score']} | {c.get('maturity', 'stub')} |"
            )
    return "\n".join(out) + "\n"


def main() -> None:
    text = render(json.loads(CATALOGUE.read_text(encoding="utf-8")))
    if "--check" in sys.argv[1:]:
        if DOC.read_text(encoding="utf-8") != text:
            sys.exit(f"{DOC.relative_to(ROOT)} is stale — run: python scripts/gen_connector_catalogue.py")
        print(f"{DOC.relative_to(ROOT)} is up to date")
        return
    DOC.write_text(text, encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
