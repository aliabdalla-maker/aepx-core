#!/usr/bin/env python3
"""Fail CI for malformed workflows, unresolved conflicts, or missing event triggers."""
from pathlib import Path
import sys
import yaml

root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
errors = []
count = 0
for path in sorted(root.glob("*.yml")) + sorted(root.glob("*.yaml")):
    count += 1
    source = path.read_text(encoding="utf-8")
    for number, line in enumerate(source.splitlines(), 1):
        if line.startswith(("<<<<<<< ", "=======", ">>>>>>> ")):
            errors.append(f"{path.name}:{number}: unresolved merge conflict")
    try:
        doc = yaml.load(source, Loader=yaml.BaseLoader)
        if not isinstance(doc, dict):
            errors.append(f"{path.name}: YAML root must be a mapping")
        elif "on" not in doc:
            errors.append(f"{path.name}: missing on trigger")
        elif not isinstance(doc.get("jobs"), dict) or not doc["jobs"]:
            errors.append(f"{path.name}: missing jobs mapping")
    except yaml.YAMLError as exc:
        errors.append(f"{path.name}: invalid YAML: {exc}")
if not count:
    errors.append("no workflow files found")
for error in errors:
    print("ERROR:", error, file=sys.stderr)
print(f"Checked {count} workflows; errors={len(errors)}")
sys.exit(bool(errors))
