"""Tests for the distribution tooling (no network, no credentials)."""
import hashlib
import json

import pytest

import play_upload
import verify_artifacts


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}
        self.text = json.dumps(self._body)
        self.content = self.text.encode()

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, version_code=7, fail_on=None):
        self.calls = []
        self.version_code = version_code
        self.fail_on = fail_on

    def _record(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if self.fail_on and self.fail_on in url:
            return Resp(500, {"error": "boom"})
        if url.endswith("/edits"):
            return Resp(200, {"id": "E1"})
        if "/bundles" in url:
            return Resp(200, {"versionCode": self.version_code})
        return Resp(200, {})

    def post(self, url, **kw): return self._record("POST", url, **kw)
    def put(self, url, **kw): return self._record("PUT", url, **kw)
    def delete(self, url, **kw): return self._record("DELETE", url, **kw)


@pytest.fixture
def aab(tmp_path):
    f = tmp_path / "app-release.aab"
    f.write_bytes(b"PK\x03\x04bundle")
    return f


def test_upload_is_internal_draft_only(aab):
    s = FakeSession()
    out = play_upload.upload(s, aab, 7, "0.2.0 (7)")
    track_calls = [c for c in s.calls if c[0] == "PUT"]
    assert len(track_calls) == 1
    _, url, kw = track_calls[0]
    assert url.endswith("/tracks/internal")
    assert kw["json"]["releases"] == [{"name": "0.2.0 (7)", "versionCodes": ["7"], "status": "draft"}]
    assert any(u.endswith("/edits/E1:commit") for _, u, _ in s.calls)
    assert out["sha256"] == hashlib.sha256(aab.read_bytes()).hexdigest()
    assert all(play_upload.PACKAGE in u for _, u, _ in s.calls)


def test_version_mismatch_abandons_edit(aab):
    s = FakeSession(version_code=6)
    with pytest.raises(play_upload.PlayUploadError, match="versionCode"):
        play_upload.upload(s, aab, 7, "x")
    assert s.calls[-1][0] == "DELETE"
    assert not any(":commit" in u for _, u, _ in s.calls)


def test_failed_commit_abandons_edit(aab):
    s = FakeSession(fail_on=":commit")
    with pytest.raises(play_upload.PlayUploadError, match="edits.commit"):
        play_upload.upload(s, aab, 7, "x")
    assert s.calls[-1][0] == "DELETE"


def test_rejects_non_aab(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"x")
    with pytest.raises(play_upload.PlayUploadError):
        play_upload.upload(FakeSession(), apk, 1, "x")


def test_verify_artifacts_round_trip(tmp_path):
    f = tmp_path / "AEP-X-0.2.0.dmg"
    f.write_bytes(b"dmg")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"filename": f.name, "sha256": hashlib.sha256(b"dmg").hexdigest()}]))
    assert verify_artifacts.verify(tmp_path, manifest) == [f.name]
    f.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="mismatch"):
        verify_artifacts.verify(tmp_path, manifest)


def test_verify_artifacts_rejects_path_traversal(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"filename": "../x", "sha256": "0" * 64}]))
    with pytest.raises(ValueError):
        verify_artifacts.verify(tmp_path, manifest)


import generate_downloads as gd

GOOD = {"platform": "macos", "label": "macOS", "filename": "AEP-X.dmg", "signed": True, "bytes": 120_000_000,
        "sha256": "a" * 64, "url": "https://downloads.softwareequality.com/aepx/0.2.0/AEP-X.dmg"}


def test_download_button_only_for_signed_checksummed_official_host():
    assert gd.is_live(GOOD)
    for bad in [{**GOOD, "signed": False}, {**GOOD, "sha256": None}, {**GOOD, "sha256": "A" * 64},
                {**GOOD, "bytes": 0}, {**GOOD, "url": "http://downloads.softwareequality.com/x.dmg"},
                {**GOOD, "url": "https://evil.example/x.dmg"},
                {**GOOD, "url": "https://downloads.softwareequality.com.evil.example/x.dmg"},
                {**GOOD, "filename": "../x.dmg"}]:
        assert not gd.is_live(bad), bad


def test_store_links_need_official_store_host():
    assert gd.is_live({"platform": "store", "url": "https://play.google.com/store/apps/details?id=x"})
    assert not gd.is_live({"platform": "store", "url": "https://play.google.com.evil.example/"})
    assert not gd.is_live({"platform": "plugin", "url": None})


def test_render_escapes_and_shows_pricing():
    page = gd.render({"version": "1", "updated": "2026-11-15", "artifacts": [
        GOOD, {"platform": "linux", "label": "<script>x</script>", "signed": False}]})
    assert "Download (120 MB)" in page and "SHA-256 " + "a" * 64 in page
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "30 days free" in page and "£4.99/month" in page and "95% fewer ads" in page
    assert "1 of 2 downloads available" in page


def test_committed_page_matches_manifest():
    import json
    from pathlib import Path
    here = Path(gd.__file__).parent
    page = gd.render(json.loads((here / "releases.json").read_text(encoding="utf-8")))
    assert (here / "website-downloads.html").read_text(encoding="utf-8") == page
    assert "0 of 15 downloads available" in page  # nothing is offered before signed builds exist
