"""Build a single-file agent binary for the current OS/arch with PyInstaller and write SHA-256 sums.
Usage: python packaging/build.py OUT_DIR"""
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
system = {"Windows": "windows", "Darwin": "macos"}.get(platform.system(), "linux")
arch = {"AMD64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
common = ["--onefile", "--clean", "--paths", str(AGENT), "--paths", str(AGENT.parent / "detection"),
          "--distpath", str(out), "--workpath", str(out / "build"), "--specpath", str(out / "build")]
name = f"aav-agent-{system}-{arch}"
subprocess.run([sys.executable, "-m", "PyInstaller", *common, "--name", name, str(AGENT / "aav_agent" / "__main__.py")], check=True)
if system == "windows":
    subprocess.run([sys.executable, "-m", "PyInstaller", *common, "--hidden-import", "win32timezone", "--name",
                    f"aav-agent-service-{system}-{arch}", str(HERE / "windows_service.py")], check=True)
sums = []
for f in sorted(out.iterdir()):
    if f.is_file() and f.name.startswith("aav-agent"):
        sums.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}")
(out / f"SHA256SUMS-{system}-{arch}.txt").write_text("\n".join(sums) + "\n")
print("\n".join(sums))
