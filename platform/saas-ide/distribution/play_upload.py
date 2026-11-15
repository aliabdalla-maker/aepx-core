"""Upload a signed AAB to Google Play as a DRAFT release on the INTERNAL testing track.

Deliberately narrow:
  * the only track is "internal" and the only status is "draft" -- an owner must still roll the
    release out in Play Console, so this script can never publish to testers or production;
  * the package name is fixed to the companion app;
  * credentials come from a service-account JSON file path (never an argument value or a log line).

Uses the Android Publisher API v3 edits flow: insert -> bundles.upload -> tracks.update -> commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Protocol

PACKAGE = "com.equalitysoftware.aepx.companion"
TRACK = "internal"
STATUS = "draft"
API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
UPLOAD_API = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
MAX_AAB_BYTES = 200 * 1024 * 1024


class PlayUploadError(RuntimeError):
    pass


class Session(Protocol):
    def post(self, url: str, **kwargs): ...
    def put(self, url: str, **kwargs): ...
    def delete(self, url: str, **kwargs): ...


def _ok(response, step: str) -> dict:
    if response.status_code // 100 != 2:
        # Play error bodies do not contain credentials; truncate anyway to keep logs small.
        raise PlayUploadError(f"{step} failed with HTTP {response.status_code}: {response.text[:300]}")
    return response.json() if response.content else {}


def upload(session: Session, aab: Path, version_code: int, release_name: str) -> dict:
    if aab.suffix != ".aab" or not aab.is_file() or aab.is_symlink():
        raise PlayUploadError("A regular .aab file is required")
    data = aab.read_bytes()
    if not data or len(data) > MAX_AAB_BYTES:
        raise PlayUploadError("AAB is empty or too large")
    if version_code < 1:
        raise PlayUploadError("versionCode must be positive")

    base = f"{API}/{PACKAGE}"
    edit_id = _ok(session.post(f"{base}/edits", json={}), "edits.insert")["id"]
    try:
        bundle = _ok(session.post(
            f"{UPLOAD_API}/{PACKAGE}/edits/{edit_id}/bundles",
            params={"uploadType": "media"},
            headers={"Content-Type": "application/octet-stream"},
            data=data,
        ), "bundles.upload")
        if int(bundle.get("versionCode", -1)) != version_code:
            raise PlayUploadError(f"Uploaded bundle has versionCode {bundle.get('versionCode')}, expected {version_code}")
        _ok(session.put(f"{base}/edits/{edit_id}/tracks/{TRACK}", json={
            "track": TRACK,
            "releases": [{"name": release_name[:50], "versionCodes": [str(version_code)], "status": STATUS}],
        }), "tracks.update")
        _ok(session.post(f"{base}/edits/{edit_id}:commit"), "edits.commit")
    except Exception:
        session.delete(f"{base}/edits/{edit_id}")  # abandon the edit; nothing is left half-applied
        raise
    return {"package": PACKAGE, "track": TRACK, "status": STATUS, "versionCode": version_code,
            "sha256": hashlib.sha256(data).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aab", type=Path, required=True)
    parser.add_argument("--version-code", type=int, required=True)
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--service-account-file", type=Path, required=True)
    args = parser.parse_args()

    from google.auth.transport.requests import AuthorizedSession  # imported late: tests need no Google libs
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(str(args.service_account_file), scopes=[SCOPE])
    print(json.dumps(upload(AuthorizedSession(creds), args.aab, args.version_code, args.release_name)))


if __name__ == "__main__":
    main()
