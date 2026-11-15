"""Social publishing adapters for the Media Studio.

  * mock       – free, records a fake post id (demos/tests).
  * mastodon   – POST {instance}/api/v1/statuses            (IDE_SOCIAL_MASTODON_URL, IDE_SOCIAL_MASTODON_TOKEN)
  * x          – POST https://api.x.com/2/tweets             (IDE_SOCIAL_X_USER_TOKEN: OAuth 2.0 user token, tweet.write)
  * linkedin   – POST https://api.linkedin.com/rest/posts    (IDE_SOCIAL_LINKEDIN_TOKEN, _AUTHOR_URN, _VERSION YYYYMM)
  * youtube / tiktok / instagram – "export" mode: these require media uploads and app review, so the approved
    post is packaged (caption + media links) for manual upload rather than published by the API.

A platform is usable only if listed in IDE_SOCIAL_PLATFORMS_ENABLED and fully configured. media.py publishes
only posts approved by an owner/admin, bound to the post's content digest.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class SocialError(Exception):
    """Safe to store and show: never contains tokens or raw response bodies."""


@dataclass
class Published:
    state: str  # published | exported
    external_id: str | None = None
    external_url: str | None = None
    package: dict | None = None


def enabled_names() -> set[str]:
    return {n.strip() for n in os.getenv("IDE_SOCIAL_PLATFORMS_ENABLED", "").split(",") if n.strip()}


class Platform:
    name = ""
    limit = 5000
    mode = "api"
    env: tuple[str, ...] = ()

    def configured(self) -> bool:
        return self.name in enabled_names() and all(os.getenv(e, "") for e in self.env)

    def validate(self, body: str) -> None:
        if not body.strip():
            raise ValueError("Post text is empty")
        if len(body) > self.limit:
            raise ValueError(f"{self.name} posts are limited to {self.limit} characters")

    def publish(self, post_id: str, body: str, media_links: list[str], http=httpx) -> Published:
        raise NotImplementedError


class MockPlatform(Platform):
    name = "mock"

    def publish(self, post_id, body, media_links, http=httpx):
        return Published("published", external_id="mock-" + post_id[:8], external_url=None)


class MastodonPlatform(Platform):
    name = "mastodon"
    limit = 500
    env = ("IDE_SOCIAL_MASTODON_URL", "IDE_SOCIAL_MASTODON_TOKEN")

    def configured(self):
        return super().configured() and os.getenv("IDE_SOCIAL_MASTODON_URL", "").startswith("https://")

    def publish(self, post_id, body, media_links, http=httpx):
        base = os.environ["IDE_SOCIAL_MASTODON_URL"].rstrip("/")
        text = body if not media_links else body + "\n\n" + "\n".join(media_links)
        r = http.post(f"{base}/api/v1/statuses", timeout=TIMEOUT, data={"status": text[: self.limit]},
                      headers={"Authorization": "Bearer " + os.environ["IDE_SOCIAL_MASTODON_TOKEN"],
                               "Idempotency-Key": post_id})
        if r.status_code != 200:
            raise SocialError(f"Mastodon publish failed (HTTP {r.status_code})")
        data = r.json()
        return Published("published", external_id=str(data.get("id"))[:255], external_url=data.get("url"))


class XPlatform(Platform):
    name = "x"
    limit = 280
    env = ("IDE_SOCIAL_X_USER_TOKEN",)

    def publish(self, post_id, body, media_links, http=httpx):
        r = http.post("https://api.x.com/2/tweets", timeout=TIMEOUT, json={"text": body},
                      headers={"Authorization": "Bearer " + os.environ["IDE_SOCIAL_X_USER_TOKEN"]})
        if r.status_code not in (200, 201):
            raise SocialError(f"X publish failed (HTTP {r.status_code})")
        tweet_id = str(r.json()["data"]["id"])
        if not re.fullmatch(r"\d{1,30}", tweet_id):
            raise SocialError("X returned an invalid post id")
        return Published("published", external_id=tweet_id, external_url=f"https://x.com/i/web/status/{tweet_id}")


class LinkedInPlatform(Platform):
    name = "linkedin"
    limit = 3000
    env = ("IDE_SOCIAL_LINKEDIN_TOKEN", "IDE_SOCIAL_LINKEDIN_AUTHOR_URN", "IDE_SOCIAL_LINKEDIN_VERSION")

    def configured(self):
        return (super().configured()
                and re.fullmatch(r"urn:li:(person|organization):[A-Za-z0-9_-]+", os.getenv("IDE_SOCIAL_LINKEDIN_AUTHOR_URN", "")) is not None
                and re.fullmatch(r"\d{6}", os.getenv("IDE_SOCIAL_LINKEDIN_VERSION", "")) is not None)

    def publish(self, post_id, body, media_links, http=httpx):
        text = body if not media_links else body + "\n\n" + "\n".join(media_links)
        r = http.post("https://api.linkedin.com/rest/posts", timeout=TIMEOUT, headers={
            "Authorization": "Bearer " + os.environ["IDE_SOCIAL_LINKEDIN_TOKEN"],
            "LinkedIn-Version": os.environ["IDE_SOCIAL_LINKEDIN_VERSION"],
            "X-Restli-Protocol-Version": "2.0.0"}, json={
            "author": os.environ["IDE_SOCIAL_LINKEDIN_AUTHOR_URN"], "commentary": text[: self.limit],
            "visibility": "PUBLIC", "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []}})
        if r.status_code != 201:
            raise SocialError(f"LinkedIn publish failed (HTTP {r.status_code})")
        urn = r.headers.get("x-restli-id", "")[:255] or None
        return Published("published", external_id=urn,
                         external_url=f"https://www.linkedin.com/feed/update/{urn}/" if urn else None)


class ExportPlatform(Platform):
    """Media-first networks: produce an upload package instead of calling an API."""
    mode = "export"

    def __init__(self, name: str, limit: int):
        self.name, self.limit = name, limit

    def configured(self):
        return self.name in enabled_names()

    def publish(self, post_id, body, media_links, http=httpx):
        return Published("exported", package={"platform": self.name, "caption": body, "media": media_links,
                                              "instructions": f"Upload the media to {self.name} and paste the caption."})


PLATFORMS: dict[str, Platform] = {p.name: p for p in (
    MockPlatform(), MastodonPlatform(), XPlatform(), LinkedInPlatform(),
    ExportPlatform("youtube", 5000), ExportPlatform("tiktok", 2200), ExportPlatform("instagram", 2200))}


def get(name: str) -> Platform:
    platform = PLATFORMS.get(name)
    if platform is None:
        raise ValueError("unknown platform")
    return platform


def capabilities() -> dict:
    return {n: {"mode": p.mode, "limit": p.limit, "configured": p.configured()} for n, p in PLATFORMS.items()}
