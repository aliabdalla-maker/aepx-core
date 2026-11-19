#!/usr/bin/env python3
"""Validate private OCI credentials without printing their values."""
import os
import re
import sys
from pathlib import Path

env_file = Path(__file__).resolve().parents[2] / ".env"
if not env_file.exists():
    sys.exit("ERROR: .env missing")
pairs = {}
for line in env_file.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        sys.exit("ERROR: invalid .env line")
    key, value = line.split("=", 1)
    if key in pairs:
        sys.exit(f"ERROR: duplicate key {key}")
    pairs[key] = value
required = ["AEPX_POSTGRES_PASSWORD", "AEPX_NEO4J_PASSWORD", "AEPX_IDENTITY_JWT_SECRET", "AEPX_INTERNAL_SERVICE_KEY"]
for key in required:
    value = pairs.get(key, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", value):
        sys.exit(f"ERROR: {key} must be 24-128 URL-safe characters")
    if value.lower().startswith(("test", "demo", "password", "change", "aepx_dev", "citestonly")):
        sys.exit(f"ERROR: {key} looks like a placeholder")
if len({pairs[k] for k in required}) != len(required):
    sys.exit("ERROR: PostgreSQL and Neo4j secrets must differ")
scoped = ["AEPX_REGISTRY_IDENTITY_KEY", "AEPX_REGISTRY_WRITE_KEY", "AEPX_TRUST_WRITE_KEY"]
for key in scoped:
    value = pairs.get(key, "")
    if value and not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value):
        sys.exit(f"ERROR: {key} must be 32-128 URL-safe characters")
configured = [pairs[k] for k in scoped if pairs.get(k)]
if len(configured) != len(set(configured)) or any(v in (pairs[k] for k in required) for v in configured):
    sys.exit("ERROR: scoped credentials must be distinct from each other and legacy credentials")
if pairs.get("AEPX_REQUIRE_SCOPED_KEYS", "false").lower() == "true":
    if any(not pairs.get(k) for k in scoped):
        sys.exit("ERROR: strict scoped mode requires all three dedicated service credentials")
elif pairs.get("AEPX_REQUIRE_SCOPED_KEYS", "false").lower() not in ("false", ""):
    sys.exit("ERROR: AEPX_REQUIRE_SCOPED_KEYS must be true or false")
if env_file.is_symlink():
    sys.exit("ERROR: .env must not be a symlink")
if os.name == "posix" and env_file.stat().st_mode & 0o077:
    sys.exit("ERROR: .env must not be group/world accessible; chmod 600 .env")
print("PASS: OCI secret format and file permissions validated (values hidden)")
