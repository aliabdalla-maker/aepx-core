#!/usr/bin/env python3
"""Fail-closed scoped credential check before OCI staging startup."""
import os
import re
import sys
from pathlib import Path

SCOPED=("AEPX_REGISTRY_IDENTITY_KEY","AEPX_REGISTRY_WRITE_KEY","AEPX_TRUST_WRITE_KEY")
LEGACY=("AEPX_POSTGRES_PASSWORD","AEPX_NEO4J_PASSWORD",
        "AEPX_IDENTITY_JWT_SECRET","AEPX_INTERNAL_SERVICE_KEY")
PATTERN=re.compile(r"[A-Za-z0-9_-]{32,128}\Z")

def validate(env):
    if env.get("AEPX_REQUIRE_SCOPED_KEYS")!="true":
        raise ValueError("strict scoped-key mode required for staging")
    values=[]
    for key in SCOPED:
        value=env.get(key,"")
        if not isinstance(value,str) or not PATTERN.fullmatch(value):
            raise ValueError(f"{key} requires 32-128 URL-safe characters")
        values.append(value)
    if len(set(values))!=len(values):
        raise ValueError("scoped credentials must be mutually distinct")
    if any(value==env.get(key) for value in values for key in LEGACY):
        raise ValueError("scoped credentials must differ from shared and database secrets")
    return True

def effective_env(path=Path(".env"),environ=None):
    """Parse the Compose .env subset without sourcing shell code."""
    values={}
    if path.is_file():
        for line in path.read_text().splitlines():
            line=line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError("malformed .env entry")
            key,value=line.split("=",1)
            key=key.strip()
            if key in values:
                raise ValueError("duplicate .env key")
            values[key]=value.strip().strip('"').strip("'")
    values.update(os.environ if environ is None else environ)
    return values

if __name__=="__main__":
    try:
        validate(effective_env())
    except ValueError as exc:
        print(f"BLOCKED: {exc}",file=sys.stderr)
        raise SystemExit(3)
    print("PASS: distinct scoped credentials validated")
