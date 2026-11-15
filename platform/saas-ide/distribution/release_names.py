"""Copy electron-builder outputs to the fixed download names used on softwareequality.com.

    python release_names.py <dist dir> <out dir>

The website links to these names, so they must never change. Unknown or duplicate
outputs fail the build rather than being published under a guessed name.
"""
import re
import shutil
import sys
from pathlib import Path

ARM = re.compile(r"(arm64|aarch64)", re.I)


def fixed_name(name: str) -> str | None:
    arm = bool(ARM.search(name))
    lower = name.lower()
    if lower.endswith((".blockmap", ".yml", ".yaml")):
        return None  # updater metadata, not a download
    if lower.endswith(".exe"):
        if "portable" in lower:
            return "AEP-X-IDE-Windows-Portable.exe"
        if "setup" in lower:
            return "AEP-X-IDE-Windows-Setup.exe"
    if lower.endswith(".dmg"):
        return f"AEP-X-IDE-macOS-{'AppleSilicon' if arm else 'Intel'}.dmg"
    if lower.endswith(".zip") and "mac" in lower:
        return f"AEP-X-IDE-macOS-{'AppleSilicon' if arm else 'Intel'}.zip"
    if lower.endswith(".appimage"):
        return f"AEP-X-IDE-Linux-{'arm64' if arm else 'x86_64'}.AppImage"
    if lower.endswith(".deb"):
        return f"AEP-X-IDE-Linux-{'arm64' if arm else 'amd64'}.deb"
    if lower.endswith(".rpm"):
        return f"AEP-X-IDE-Linux-{'aarch64' if arm else 'x86_64'}.rpm"
    if lower.endswith(".tar.gz"):
        return f"AEP-X-IDE-Linux-{'arm64' if arm else 'x64'}.tar.gz"
    raise SystemExit(f"Unrecognised build output: {name}")


def main(dist: str, out: str) -> int:
    src, dst = Path(dist), Path(out)
    dst.mkdir(parents=True, exist_ok=True)
    seen: dict[str, str] = {}
    for f in sorted(p for p in src.iterdir() if p.is_file()):
        target = fixed_name(f.name)
        if target is None:
            continue
        if target in seen:
            raise SystemExit(f"Two outputs map to {target}: {seen[target]} and {f.name}")
        seen[target] = f.name
        shutil.copy2(f, dst / target)
        print(f"{f.name} -> {target}")
    if not seen:
        raise SystemExit("No installers found")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
