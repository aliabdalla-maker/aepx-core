#!/usr/bin/env python3
"""Read-only registry platform check for the two external staging images.

Uses Docker manifest inspection only. Does not pull images or create resources.
"""
import json
import platform
import subprocess
import sys

IMAGES=("pgvector/pgvector:pg16","redis:7")
ARCH={"x86_64":"amd64","amd64":"amd64","aarch64":"arm64","arm64":"arm64"}

def supports(manifest, architecture):
    if "manifests" in manifest:
        return any(item.get("platform",{}).get("os")=="linux" and
                   item.get("platform",{}).get("architecture")==architecture
                   for item in manifest["manifests"])
    # A single-image manifest does not prove which architecture was published.
    return False

def verify(run=subprocess.run, machine=None):
    arch=ARCH.get(platform.machine() if machine is None else machine)
    if not arch:
        raise RuntimeError("unsupported host architecture")
    for image in IMAGES:
        result=run(["docker","manifest","inspect",image],capture_output=True,text=True,timeout=45)
        if result.returncode:
            raise RuntimeError(f"manifest unavailable: {image}")
        try:
            manifest=json.loads(result.stdout)
        except (ValueError,TypeError) as exc:
            raise RuntimeError(f"invalid manifest: {image}") from exc
        if not supports(manifest,arch):
            raise RuntimeError(f"linux/{arch} not verified for {image}")
    return arch

if __name__=="__main__":
    try:
        print("PASS: external image manifests support linux/"+verify())
    except (RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
        print("BLOCKED: "+str(exc),file=sys.stderr)
        raise SystemExit(3)
