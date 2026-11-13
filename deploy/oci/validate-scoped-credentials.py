#!/usr/bin/env python3
"""Fail-closed validation of scoped service credentials for OCI staging start.

Runs before any Docker Compose mutation. Never print secret values.
"""
import hmac
import os
import sys

NAMES=(
    "AEPX_REGISTRY_IDENTITY_KEY",
    "AEPX_REGISTRY_WRITE_KEY",
    "AEPX_TRUST_WRITE_KEY",
)
def validate(env):
    if env.get("AEPX_REQUIRE_SCOPED_KEYS") != "true":
        raise ValueError("AEPX_REQUIRE_SCOPED_KEYS must be true for staging startup")
    secrets=[]
    for name in NAMES:
        value=env.get(name,"")
        if len(value)<32 or value.strip()!=value or any(c in value for c in "\r\n"):
            raise ValueError(f"{name} must be a distinct, nonempty credential of at least 32 characters")
        secrets.append(value)
    for i in range(len(secrets)):
        for j in range(i):
            if hmac.compare_digest(secrets[i],secrets[j]):
                raise ValueError("scoped service credentials must be distinct")
    return True

if __name__=="__main__":
    try:
        validate(os.environ)
    except ValueError as exc:
        print(f"BLOCKED: {exc}",file=sys.stderr)
        raise SystemExit(3)
    print("PASS: scoped staging credentials configured")
