#!/usr/bin/env python3
"""Static OCI staging Compose guard; does not validate tenancy, cost or security groups."""
import pathlib
import re
import sys
p=pathlib.Path(__file__).resolve().parents[1]/"deploy/oci-always-free/compose.yml"
s=p.read_text()
errors=[]
if "127.0.0.1:8000:8000" not in s:errors.append("gateway must bind loopback")
if re.search(r'^\s*ports:',s,re.M) and len(re.findall(r'^\s*ports:',s,re.M))!=1:
    errors.append("only gateway may publish a host port")
if "AEPX_POSTGRES_PASSWORD:?" not in s:errors.append("required database password absent")
if "aepx_dev_only" in s:errors.append("development credentials forbidden")
if "latest" in s:errors.append("unpinned latest image forbidden")
if errors:
    print("\n".join(errors),file=sys.stderr)
    sys.exit(1)
print("OCI staging Compose static guard passed; runtime and security validation still required")
