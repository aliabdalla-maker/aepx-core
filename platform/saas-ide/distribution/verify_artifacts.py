"""Verify draft installer artifacts against a supplied release manifest.

No artifact is published or signed by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path

def verify(directory: Path, manifest: Path) -> list[str]:
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError("Non-empty artifact manifest required")
    verified = []
    for item in entries:
        name, digest = item["filename"], item["sha256"]
        if Path(name).name != name or len(digest) != 64:
            raise ValueError("Invalid artifact filename or checksum")
        artifact = directory / name
        if not artifact.is_file() or artifact.is_symlink():
            raise FileNotFoundError(name)
        h = hashlib.sha256()
        with artifact.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        if h.hexdigest() != digest.lower():
            raise ValueError("Checksum mismatch: " + name)
        verified.append(name)
    return verified

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print("Verified:", ", ".join(verify(args.directory, args.manifest)))
