#!/usr/bin/env python3
"""Read-only release evidence validator for isolated OCI staging.

The approval flags alone are insufficient: require recent, nonempty operator
evidence files. This does not itself verify that a restore or image build ran.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

EVIDENCE=(
    ("AEPX_BACKUP_RESTORE_VERIFIED","AEPX_BACKUP_RESTORE_EVIDENCE"),
    ("AEPX_IMAGE_PLATFORMS_VERIFIED","AEPX_IMAGE_PLATFORM_EVIDENCE"),
)

def validate(env, now=None):
    now=datetime.now(timezone.utc) if now is None else now
    for approval,variable in EVIDENCE:
        if env.get(approval)!="yes":
            raise ValueError(f"{approval} must be yes")
        filename=env.get(variable,"")
        if not filename:
            raise ValueError(f"{variable} required")
        path=Path(filename).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{variable} must reference a regular non-symlink file")
        stat=path.stat()
        if stat.st_size<32 or stat.st_size>1024*1024:
            raise ValueError(f"{variable} evidence size invalid")
        modified=datetime.fromtimestamp(stat.st_mtime,timezone.utc)
        if modified>now+timedelta(minutes=5) or now-modified>timedelta(days=7):
            raise ValueError(f"{variable} evidence must be recent (7 days)")
    return True

if __name__=="__main__":
    try:
        validate(os.environ)
    except (ValueError,OSError) as exc:
        print("BLOCKED: "+str(exc),file=sys.stderr)
        raise SystemExit(3)
    print("PASS: operator release evidence files present and recent")
