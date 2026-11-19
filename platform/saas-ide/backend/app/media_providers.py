"""AI media provider adapters for the Media Studio.

Safety model (enforced by media.py, documented here):
  * A provider is usable only when it is listed in IDE_MEDIA_PROVIDERS_ENABLED *and* its API key is set.
    Nothing is enabled by default, so a fresh deployment cannot spend money.
  * "mock" (IDE_MEDIA_PROVIDERS_ENABLED=mock) produces deterministic, free placeholder output for demos and tests.
  * Adapters are only called for a job a human approved, bound to the job's content digest.
  * Errors are reduced to short, secret-free messages before they are stored.

Estimates are indicative list prices in pence, shown to the approver before any paid call.
"""
from __future__ import annotations

import base64
import html
import io
import os
import re
import struct
import wave
from dataclasses import dataclass, field

import httpx

KINDS = ("image", "video", "music", "voice", "script")
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_ASSET_BYTES = 20 * 1024 * 1024


class MediaProviderError(Exception):
    """Safe to show to users: never contains credentials or raw provider bodies."""


@dataclass
class Result:
    state: str  # running | succeeded | failed
    external_id: str | None = None
    result_url: str | None = None
    result_text: str | None = None
    asset: bytes | None = None
    content_type: str | None = None
    error: str | None = None
    meta: dict = field(default_factory=dict)


def enabled_names() -> set[str]:
    return {n.strip() for n in os.getenv("IDE_MEDIA_PROVIDERS_ENABLED", "").split(",") if n.strip()}


def _https(url: object) -> bool:
    return isinstance(url, str) and url.startswith("https://") and len(url) <= 2048


def _fail(response: httpx.Response, step: str) -> MediaProviderError:
    return MediaProviderError(f"{step} failed (HTTP {response.status_code})")


class Provider:
    name = ""
    kinds: tuple[str, ...] = ()
    key_env = ""

    def configured(self) -> bool:
        if self.name not in enabled_names():
            return False
        return bool(os.getenv(self.key_env, "")) if self.key_env else True

    def key(self) -> str:
        value = os.getenv(self.key_env, "")
        if not value:
            raise MediaProviderError(f"{self.name} is not configured")
        return value

    def validate(self, kind: str, params: dict) -> dict:
        raise NotImplementedError

    def estimate_pence(self, kind: str, prompt: str, params: dict) -> int:
        return 0

    def submit(self, kind: str, prompt: str, params: dict, http=httpx) -> Result:
        raise NotImplementedError

    def poll(self, external_id: str, http=httpx) -> Result:
        raise MediaProviderError("This provider completes synchronously")


# ---------- shared parameter rules ----------

IMAGE_SIZES = {"1024x1024", "1792x1024", "1024x1792"}
VIDEO_RATIOS = {"1280:720", "720:1280", "960:960"}
VOICE_ID = re.compile(r"^[A-Za-z0-9]{8,40}$")


def _common(kind: str, params: dict) -> dict:
    if not isinstance(params, dict) or len(params) > 10:
        raise ValueError("params must be a small object")
    if kind == "image":
        size = params.get("size", "1024x1024")
        if size not in IMAGE_SIZES:
            raise ValueError(f"size must be one of {sorted(IMAGE_SIZES)}")
        return {"size": size}
    if kind == "video":
        duration = params.get("duration_s", 5)
        ratio = params.get("ratio", "1280:720")
        if duration not in (5, 10):
            raise ValueError("duration_s must be 5 or 10")
        if ratio not in VIDEO_RATIOS:
            raise ValueError(f"ratio must be one of {sorted(VIDEO_RATIOS)}")
        out = {"duration_s": duration, "ratio": ratio}
        if params.get("image_job_id"):
            out["image_job_id"] = str(params["image_job_id"])[:36]
        elif params.get("image_url"):
            if not _https(params["image_url"]):
                raise ValueError("image_url must be https")
            out["image_url"] = params["image_url"]
        return out
    if kind == "music":
        length = params.get("length_s", 30)
        if not isinstance(length, int) or isinstance(length, bool) or not 10 <= length <= 300:
            raise ValueError("length_s must be an integer between 10 and 300")
        return {"length_s": length}
    if kind == "voice":
        voice = params.get("voice_id", "")
        if voice and not VOICE_ID.match(str(voice)):
            raise ValueError("voice_id is invalid")
        return {"voice_id": voice} if voice else {}
    if kind == "script":
        tokens = params.get("max_tokens", 1200)
        if not isinstance(tokens, int) or isinstance(tokens, bool) or not 100 <= tokens <= 4000:
            raise ValueError("max_tokens must be between 100 and 4000")
        return {"max_tokens": tokens}
    raise ValueError("unknown kind")


# ---------- mock (free, deterministic) ----------

def _silent_wav(seconds: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 8000 * min(seconds, 5))
    return buf.getvalue()


class MockProvider(Provider):
    name = "mock"
    kinds = KINDS

    def validate(self, kind, params):
        return _common(kind, params)

    def submit(self, kind, prompt, params, http=httpx):
        label = html.escape(prompt[:120])
        if kind == "image":
            svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="576" viewBox="0 0 1024 576">'
                   '<rect width="1024" height="576" fill="#0b1020"/><rect x="24" y="24" width="976" height="528" '
                   'fill="none" stroke="#7acbff" stroke-width="4" rx="16"/><text x="512" y="270" fill="#e7ecf7" '
                   'font-family="sans-serif" font-size="28" text-anchor="middle">MOCK IMAGE</text>'
                   f'<text x="512" y="320" fill="#a9b4c8" font-family="sans-serif" font-size="18" '
                   f'text-anchor="middle">{label}</text></svg>')
            return Result("succeeded", asset=svg.encode(), content_type="image/svg+xml")
        if kind in ("music", "voice"):
            return Result("succeeded", asset=_silent_wav(params.get("length_s", 3)), content_type="audio/wav")
        if kind == "video":
            return Result("succeeded", result_text=f"[mock video {params['duration_s']}s {params['ratio']}] {prompt[:200]}")
        return Result("succeeded", result_text=(
            f"MOCK SCRIPT\n\nTITLE: {prompt[:80]}\n\nSCENE 1 - EXT. CITY - DAWN\nEstablishing shot.\n\n"
            "SCENE 2 - INT. STUDIO - DAY\nThe team reviews the plan.\n"))


# ---------- OpenAI: images and scripts ----------

class OpenAIProvider(Provider):
    name = "openai"
    kinds = ("image", "script")
    key_env = "IDE_MEDIA_OPENAI_API_KEY"
    base = "https://api.openai.com/v1"

    def validate(self, kind, params):
        return _common(kind, params)

    def estimate_pence(self, kind, prompt, params):
        if kind == "image":
            return 4 if params["size"] == "1024x1024" else 7
        return 1 + params.get("max_tokens", 1200) // 2000

    def submit(self, kind, prompt, params, http=httpx):
        headers = {"Authorization": "Bearer " + self.key()}
        if kind == "image":
            r = http.post(f"{self.base}/images/generations", headers=headers, timeout=TIMEOUT, json={
                "model": os.getenv("IDE_MEDIA_OPENAI_IMAGE_MODEL", "dall-e-3"), "prompt": prompt,
                "size": params["size"], "n": 1, "response_format": "b64_json"})
            if r.status_code != 200:
                raise _fail(r, "OpenAI image generation")
            data = base64.b64decode(r.json()["data"][0]["b64_json"])
            if not data or len(data) > MAX_ASSET_BYTES:
                raise MediaProviderError("OpenAI returned an empty or oversized image")
            return Result("succeeded", asset=data, content_type="image/png")
        r = http.post(f"{self.base}/chat/completions", headers=headers, timeout=TIMEOUT, json={
            "model": os.getenv("IDE_MEDIA_OPENAI_TEXT_MODEL", "gpt-4o-mini"),
            "max_tokens": params["max_tokens"],
            "messages": [
                {"role": "system", "content": "You are a professional screenwriter and creative producer. "
                 "Write production-ready scripts, shot lists and social copy. Do not imitate real people."},
                {"role": "user", "content": prompt}]})
        if r.status_code != 200:
            raise _fail(r, "OpenAI script generation")
        return Result("succeeded", result_text=r.json()["choices"][0]["message"]["content"])


# ---------- ElevenLabs: voice and music ----------

class ElevenLabsProvider(Provider):
    name = "elevenlabs"
    kinds = ("voice", "music")
    key_env = "IDE_MEDIA_ELEVENLABS_API_KEY"
    base = "https://api.elevenlabs.io/v1"

    def validate(self, kind, params):
        out = _common(kind, params)
        if kind == "voice" and not out.get("voice_id"):
            out["voice_id"] = os.getenv("IDE_MEDIA_ELEVENLABS_DEFAULT_VOICE", "")
            if not VOICE_ID.match(out["voice_id"]):
                raise ValueError("voice_id is required for ElevenLabs voice")
        return out

    def estimate_pence(self, kind, prompt, params):
        if kind == "voice":
            return max(1, len(prompt) * 25 // 1000)  # ~25p per 1,000 characters
        return max(10, params["length_s"] * 4 // 3)  # ~40p per 30 s

    def submit(self, kind, prompt, params, http=httpx):
        headers = {"xi-api-key": self.key(), "Accept": "audio/mpeg"}
        if kind == "voice":
            r = http.post(f"{self.base}/text-to-speech/{params['voice_id']}", headers=headers, timeout=TIMEOUT,
                          params={"output_format": "mp3_44100_128"},
                          json={"text": prompt, "model_id": os.getenv("IDE_MEDIA_ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2")})
            step = "ElevenLabs text-to-speech"
        else:
            r = http.post(f"{self.base}/music", headers=headers, timeout=httpx.Timeout(300.0, connect=10.0),
                          json={"prompt": prompt, "music_length_ms": params["length_s"] * 1000})
            step = "ElevenLabs music"
        if r.status_code != 200:
            raise _fail(r, step)
        if not r.content or len(r.content) > MAX_ASSET_BYTES:
            raise MediaProviderError(f"{step} returned an empty or oversized file")
        return Result("succeeded", asset=r.content, content_type="audio/mpeg")


# ---------- Runway: image-to-video (asynchronous) ----------

class RunwayProvider(Provider):
    name = "runway"
    kinds = ("video",)
    key_env = "IDE_MEDIA_RUNWAY_API_KEY"
    base = "https://api.dev.runwayml.com/v1"
    version = "2024-11-06"

    def validate(self, kind, params):
        out = _common(kind, params)
        if not out.get("image_url") and not out.get("image_job_id"):
            raise ValueError("Runway video needs a starting frame: image_job_id or image_url")
        return out

    def estimate_pence(self, kind, prompt, params):
        return 4 * params["duration_s"]  # gen4_turbo ~5 credits/s (~$0.05/s)

    def _headers(self):
        return {"Authorization": "Bearer " + self.key(), "X-Runway-Version": self.version}

    def submit(self, kind, prompt, params, http=httpx):
        image = params.get("image_data_uri") or params.get("image_url")
        if not image:
            raise MediaProviderError("No starting frame available for the video")
        r = http.post(f"{self.base}/image_to_video", headers=self._headers(), timeout=TIMEOUT, json={
            "model": os.getenv("IDE_MEDIA_RUNWAY_MODEL", "gen4_turbo"), "promptImage": image,
            "promptText": prompt[:1000], "ratio": params["ratio"], "duration": params["duration_s"]})
        if r.status_code not in (200, 201):
            raise _fail(r, "Runway video submission")
        return Result("running", external_id=str(r.json()["id"])[:255])

    def poll(self, external_id, http=httpx):
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", external_id):
            raise MediaProviderError("invalid task id")
        r = http.get(f"{self.base}/tasks/{external_id}", headers=self._headers(), timeout=TIMEOUT)
        if r.status_code != 200:
            raise _fail(r, "Runway task status")
        body = r.json()
        status = body.get("status")
        if status == "SUCCEEDED":
            outputs = [u for u in body.get("output") or [] if _https(u)]
            if not outputs:
                return Result("failed", error="Runway returned no video")
            # Runway output URLs are temporary: download the result promptly from the job page.
            return Result("succeeded", result_url=outputs[0])
        if status in ("FAILED", "CANCELLED"):
            return Result("failed", error="Runway task " + status.lower())
        return Result("running", external_id=external_id)


PROVIDERS: dict[str, Provider] = {p.name: p for p in (MockProvider(), OpenAIProvider(), ElevenLabsProvider(), RunwayProvider())}


def get(name: str) -> Provider:
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError("unknown provider")
    return provider


def capabilities() -> dict:
    return {name: {"kinds": list(p.kinds), "configured": p.configured()} for name, p in PROVIDERS.items()}
