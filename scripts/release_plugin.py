"""Cut a release of the aepx-core Claude plugin.

Keeps the version in .claude-plugin/plugin.json and .claude-plugin/marketplace.json
in step, adds a CHANGELOG entry, and prints the git commands to tag the release.

    python scripts/release_plugin.py patch|minor|major|X.Y.Z "One-line summary"
"""
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"
CHANGELOG = ROOT / ".claude-plugin" / "CHANGELOG.md"
PLUGIN_NAME = "aepx-core"


def bump(current: str, part: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", part):
        return part
    major, minor, patch = map(int, current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    sys.exit(f"unknown bump '{part}' (use patch, minor, major or X.Y.Z)")


def write_json(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    part, summary = sys.argv[1], sys.argv[2]

    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    market = json.loads(MARKET.read_text(encoding="utf-8"))
    entry = next(p for p in market["plugins"] if p["name"] == PLUGIN_NAME)
    if entry["version"] != plugin["version"]:
        sys.exit(f"versions out of sync: plugin.json {plugin['version']} vs marketplace.json {entry['version']}")

    new = bump(plugin["version"], part)
    if new == plugin["version"]:
        sys.exit(f"already at {new}")
    plugin["version"] = entry["version"] = new
    write_json(PLUGIN, plugin)
    write_json(MARKET, market)

    today = datetime.date.today().isoformat()
    log = CHANGELOG.read_text(encoding="utf-8")
    head, sep, rest = log.partition("\n## ")
    CHANGELOG.write_text(f"{head}\n## {new} — {today}\n\n- {summary}\n{sep}{rest}", encoding="utf-8")

    print(f"{PLUGIN_NAME} {plugin['version']} ready. Next:")
    print(f'  git commit -am "Release {PLUGIN_NAME} plugin v{new}"')
    print(f"  git tag -a plugin-v{new} -m \"{summary}\"")
    print(f"  git push origin master plugin-v{new}")


if __name__ == "__main__":
    main()
