"""Media Studio unit tests: providers, social adapters, storyboard/EDL, templates and the media crew.
No network: every external call goes through a recording fake."""
import os
os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")

import base64
import json

import pytest

from app import main  # noqa: F401  (load the app first, as uvicorn does; media registers on it)
from app import media, media_providers as mp, media_templates, social
from app.supervisor import plan_steps


class Resp:
    def __init__(self, status=200, body=None, content=b"", headers=None):
        self.status_code = status
        self._body = body
        self.content = content or (json.dumps(body).encode() if body is not None else b"")
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.responses.pop(0)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.responses.pop(0)


# ---------- provider enablement ----------

def test_nothing_is_enabled_by_default(monkeypatch):
    monkeypatch.delenv("IDE_MEDIA_PROVIDERS_ENABLED", raising=False)
    monkeypatch.delenv("IDE_SOCIAL_PLATFORMS_ENABLED", raising=False)
    assert not any(v["configured"] for v in mp.capabilities().values())
    assert not any(v["configured"] for v in social.capabilities().values())


def test_provider_needs_both_listing_and_key(monkeypatch):
    monkeypatch.setenv("IDE_MEDIA_PROVIDERS_ENABLED", "openai")
    monkeypatch.delenv("IDE_MEDIA_OPENAI_API_KEY", raising=False)
    assert not mp.get("openai").configured()
    monkeypatch.setenv("IDE_MEDIA_OPENAI_API_KEY", "sk-test")
    assert mp.get("openai").configured()
    monkeypatch.setenv("IDE_MEDIA_PROVIDERS_ENABLED", "mock")
    assert not mp.get("openai").configured() and mp.get("mock").configured()


@pytest.mark.parametrize("kind,params,ok", [
    ("image", {"size": "1024x1024"}, True), ("image", {"size": "4096x4096"}, False),
    ("video", {"duration_s": 5, "image_url": "https://cdn.example/a.png"}, True),
    ("video", {"duration_s": 7}, False), ("video", {"image_url": "http://cdn.example/a.png"}, False),
    ("music", {"length_s": 30}, True), ("music", {"length_s": 3}, False), ("music", {"length_s": True}, False),
    ("voice", {"voice_id": "abc"}, False), ("script", {"max_tokens": 50}, False),
])
def test_parameter_validation(kind, params, ok):
    if ok:
        mp.get("mock").validate(kind, params)
    else:
        with pytest.raises(ValueError):
            mp.get("mock").validate(kind, params)


def test_mock_outputs_are_free_and_escaped():
    m = mp.get("mock")
    image = m.submit("image", "<script>alert(1)</script>", m.validate("image", {}))
    assert image.state == "succeeded" and image.content_type == "image/svg+xml"
    assert b"<script>" not in image.asset and b"&lt;script&gt;" in image.asset
    audio = m.submit("music", "lofi", m.validate("music", {"length_s": 10}))
    assert audio.asset[:4] == b"RIFF" and audio.content_type == "audio/wav"
    assert m.estimate_pence("video", "x", {"duration_s": 5}) == 0


# ---------- real adapters, against fakes ----------

def test_openai_image_stores_bytes_not_expiring_urls(monkeypatch):
    monkeypatch.setenv("IDE_MEDIA_OPENAI_API_KEY", "sk-test")
    png = b"\x89PNG fake"
    http = FakeHttp(Resp(200, {"data": [{"b64_json": base64.b64encode(png).decode()}]}))
    r = mp.get("openai").submit("image", "poster", {"size": "1024x1024"}, http=http)
    assert r.asset == png and r.content_type == "image/png"
    _, url, kw = http.calls[0]
    assert url == "https://api.openai.com/v1/images/generations"
    assert kw["json"]["response_format"] == "b64_json" and kw["headers"]["Authorization"] == "Bearer sk-test"


def test_provider_errors_never_leak_bodies_or_keys(monkeypatch):
    monkeypatch.setenv("IDE_MEDIA_OPENAI_API_KEY", "sk-secret")
    http = FakeHttp(Resp(401, {"error": "invalid key sk-secret"}))
    with pytest.raises(mp.MediaProviderError) as exc:
        mp.get("openai").submit("script", "x", {"max_tokens": 200}, http=http)
    assert "sk-secret" not in str(exc.value) and "401" in str(exc.value)


def test_elevenlabs_voice_and_music_requests(monkeypatch):
    monkeypatch.setenv("IDE_MEDIA_ELEVENLABS_API_KEY", "xi")
    http = FakeHttp(Resp(200, content=b"ID3voice"), Resp(200, content=b"ID3music"))
    p = mp.get("elevenlabs")
    v = p.submit("voice", "Hello", {"voice_id": "VoiceId1234"}, http=http)
    m = p.submit("music", "uplifting synthwave", {"length_s": 30}, http=http)
    assert v.asset == b"ID3voice" and m.asset == b"ID3music"
    assert http.calls[0][1].endswith("/text-to-speech/VoiceId1234") and http.calls[0][2]["headers"]["xi-api-key"] == "xi"
    assert http.calls[1][1].endswith("/music") and http.calls[1][2]["json"]["music_length_ms"] == 30000


def test_runway_is_async_and_polls(monkeypatch):
    monkeypatch.setenv("IDE_MEDIA_RUNWAY_API_KEY", "rw")
    p = mp.get("runway")
    with pytest.raises(ValueError):
        p.validate("video", {"duration_s": 5})  # needs a starting frame
    http = FakeHttp(Resp(200, {"id": "task-1"}), Resp(200, {"status": "RUNNING"}),
                    Resp(200, {"status": "SUCCEEDED", "output": ["https://cdn.runway.example/v.mp4"]}))
    started = p.submit("video", "pan across city", {"duration_s": 5, "ratio": "1280:720",
                                                     "image_data_uri": "data:image/png;base64,AAAA"}, http=http)
    assert started.state == "running" and started.external_id == "task-1"
    assert http.calls[0][2]["headers"]["X-Runway-Version"] == "2024-11-06"
    assert p.poll("task-1", http=http).state == "running"
    done = p.poll("task-1", http=http)
    assert done.state == "succeeded" and done.result_url.startswith("https://")
    with pytest.raises(mp.MediaProviderError):
        p.poll("../etc", http=http)


def test_estimates_are_shown_before_spend():
    assert mp.get("runway").estimate_pence("video", "x", {"duration_s": 10}) == 40
    assert mp.get("elevenlabs").estimate_pence("music", "x", {"length_s": 30}) == 40
    assert mp.get("openai").estimate_pence("image", "x", {"size": "1792x1024"}) == 7


# ---------- social ----------

def test_platform_limits_and_enablement(monkeypatch):
    with pytest.raises(ValueError):
        social.get("x").validate("a" * 281)
    social.get("x").validate("a" * 280)
    monkeypatch.setenv("IDE_SOCIAL_PLATFORMS_ENABLED", "linkedin,mastodon")
    monkeypatch.setenv("IDE_SOCIAL_LINKEDIN_TOKEN", "t")
    monkeypatch.setenv("IDE_SOCIAL_LINKEDIN_AUTHOR_URN", "urn:li:organization:123")
    monkeypatch.delenv("IDE_SOCIAL_LINKEDIN_VERSION", raising=False)
    assert not social.get("linkedin").configured()  # version header is mandatory
    monkeypatch.setenv("IDE_SOCIAL_LINKEDIN_VERSION", "202610")
    assert social.get("linkedin").configured()
    monkeypatch.setenv("IDE_SOCIAL_MASTODON_URL", "http://insecure.example")
    monkeypatch.setenv("IDE_SOCIAL_MASTODON_TOKEN", "m")
    assert not social.get("mastodon").configured()


def test_x_and_mastodon_and_linkedin_publish(monkeypatch):
    monkeypatch.setenv("IDE_SOCIAL_X_USER_TOKEN", "xt")
    monkeypatch.setenv("IDE_SOCIAL_MASTODON_URL", "https://mastodon.example/")
    monkeypatch.setenv("IDE_SOCIAL_MASTODON_TOKEN", "mt")
    monkeypatch.setenv("IDE_SOCIAL_LINKEDIN_TOKEN", "lt")
    monkeypatch.setenv("IDE_SOCIAL_LINKEDIN_AUTHOR_URN", "urn:li:person:abc")
    monkeypatch.setenv("IDE_SOCIAL_LINKEDIN_VERSION", "202610")
    http = FakeHttp(Resp(201, {"data": {"id": "1850000000000000000"}}),
                    Resp(200, {"id": "111", "url": "https://mastodon.example/@a/111"}),
                    Resp(201, {}, headers={"x-restli-id": "urn:li:share:9"}))
    x = social.get("x").publish("p1", "hello", [], http=http)
    m = social.get("mastodon").publish("p2", "hello", ["https://cdn.example/v.mp4"], http=http)
    li = social.get("linkedin").publish("p3", "hello", [], http=http)
    assert x.external_url == "https://x.com/i/web/status/1850000000000000000"
    assert m.external_id == "111" and http.calls[1][2]["headers"]["Idempotency-Key"] == "p2"
    assert "https://cdn.example/v.mp4" in http.calls[1][2]["data"]["status"]
    assert li.external_id == "urn:li:share:9" and http.calls[2][2]["headers"]["LinkedIn-Version"] == "202610"


def test_publish_failure_is_sanitised(monkeypatch):
    monkeypatch.setenv("IDE_SOCIAL_X_USER_TOKEN", "secret-token")
    with pytest.raises(social.SocialError) as exc:
        social.get("x").publish("p", "hi", [], http=FakeHttp(Resp(403, {"detail": "secret-token revoked"})))
    assert "secret-token" not in str(exc.value)


def test_export_platforms_never_call_apis():
    out = social.get("tiktok").publish("p", "caption", ["https://cdn/v.mp4"], http=FakeHttp())
    assert out.state == "exported" and out.package["caption"] == "caption"


# ---------- digest binding ----------

def test_digest_changes_with_any_edit():
    a = media._post_digest("x", "hello", [], None)
    assert a == media._post_digest("x", "hello", [], None)
    assert a != media._post_digest("x", "hello!", [], None)
    assert a != media._post_digest("linkedin", "hello", [], None)


# ---------- film pipeline ----------

def board(**changes):
    data = json.loads(media_templates.TEMPLATES["film-pipeline"]["files"]["media/storyboard.json"])
    data.update(changes)
    return data


def test_template_storyboard_is_valid_and_exports():
    sb = media.Storyboard.model_validate(board())
    edl = media.export_edl(sb)
    assert edl.startswith("TITLE: Launch film\nFCM: NON-DROP FRAME")
    assert "001  S1WIDE   V     C        00:00:00:00 00:00:05:00 00:00:00:00 00:00:05:00" in edl
    assert "* FROM CLIP NAME: s2-desk.mp4" in edl
    script = media.export_ffmpeg(sb)
    assert script.startswith("#!/bin/sh") and "-f concat" in script and "'s1-wide.mp4'" in script


@pytest.mark.parametrize("change,message", [
    ({"timeline": [{"shot_id": "ghost", "start_s": 0, "end_s": 5}]}, "unknown shot"),
    ({"timeline": [{"shot_id": "s1-wide", "start_s": 0, "end_s": 5}, {"shot_id": "s2-desk", "start_s": 4, "end_s": 6}]}, "overlap"),
    ({"timeline": [{"shot_id": "s1-wide", "start_s": 5, "end_s": 5}]}, "after start"),
])
def test_storyboard_rejects_bad_timelines(change, message):
    with pytest.raises(ValueError, match=message):
        media.Storyboard.model_validate(board(**change))


def test_shot_ids_are_shell_safe_slugs():
    bad = board()
    bad["scenes"][0]["shots"][0]["id"] = "x'; rm -rf ~"
    with pytest.raises(ValueError):
        media.Storyboard.model_validate(bad)


def test_timecode():
    assert media.timecode(61.4, 25) == "00:01:01:10"
    assert media.timecode(3600, 24) == "01:00:00:00"


# ---------- templates and planner ----------

def test_templates_have_safe_paths_and_deploy_files():
    from app.main import safe_path
    for tid, t in media_templates.TEMPLATES.items():
        for path in t["files"]:
            assert safe_path(path) == path, (tid, path)
    for tid in ("music-player", "video-editor"):
        assert "Dockerfile" in media_templates.TEMPLATES[tid]["files"]


def test_media_crew_joins_only_media_tasks():
    assert [s["agent"] for s in plan_steps("Build an application")] == ["requirements", "architect", "developer", "verifier"]
    agents = [s["agent"] for s in plan_steps("Make a launch film with a soundtrack and a social campaign")]
    assert agents[:3] == ["requirements", "architect", "developer"] and agents[-1] == "verifier"
    assert {"producer", "composer", "director", "editor", "social-manager"} <= set(agents)
    assert not any(s["action"] in ("execute", "publish") for s in plan_steps("post a video on youtube"))
