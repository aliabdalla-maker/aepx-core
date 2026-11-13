#!/usr/bin/env python3
"""Read-only production readiness audit of the development Compose file."""
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
compose = (root / "docker-compose.yml").read_text()
issues = []
for needle in ("aepx_dev_only", "neo4j/test", "POSTGRES_PASSWORD: aepx"):
    if needle in compose:
        issues.append(f"Development credential reference: {needle}")
if re.search(r"(?m)^\s*ports:\s*\[", compose):
    issues.append("Development Compose publishes ports; always use verified loopback overlay")
if "ollama" in compose.lower():
    issues.append("Ollama model memory/storage requirements must be measured on target VM")
if "kafka" in compose.lower():
    issues.append("Kafka capacity and ARM64 image compatibility require host validation")
print("AEP-X Compose production readiness audit")
for item in issues:
    print("BLOCKER:", item)
print(f"{len(issues)} finding(s); no resources modified")
sys.exit(1 if issues else 0)
