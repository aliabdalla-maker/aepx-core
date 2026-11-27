"""Object storage (BE-05): OCI Object Storage through its Amazon S3 Compatibility API, which is part of OCI Always
Free (20 GB). Used for off-VM copies of the encrypted database backups (OCI-10); the backups are encrypted before
they reach this module, so the bucket never holds plaintext.

Configuration (all in /etc/aav/aav.env, never in git):
  AAV_OBJECT_STORE_ENDPOINT  https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
  AAV_OBJECT_STORE_REGION    e.g. uk-london-1
  AAV_OBJECT_STORE_BUCKET    e.g. aav-backups (private bucket; lifecycle rule deletes objects after N days)
  AAV_OBJECT_STORE_ACCESS_KEY / AAV_OBJECT_STORE_SECRET_KEY   an OCI "Customer Secret Key" of a dedicated user
The endpoint host must be on AAV_EGRESS_ALLOWLIST (deny-by-default egress, AX-16).

Requests are signed with AWS Signature Version 4 (path-style URLs, as OCI requires) using only the standard
library and httpx.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import httpx

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class ObjectStoreError(RuntimeError):
    pass


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_v4(*, method: str, url: str, headers: dict[str, str], payload_sha256: str, access_key: str, secret_key: str,
            region: str, now: datetime, service: str = "s3") -> dict[str, str]:
    """Return headers including Authorization for an AWS SigV4 request (query string must already be canonical)."""
    u = urlparse(url)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    h = {k.lower(): " ".join(str(v).strip().split()) for k, v in headers.items()}
    h["host"] = u.netloc
    h["x-amz-date"] = amz_date
    h["x-amz-content-sha256"] = payload_sha256
    signed = ";".join(sorted(h))
    canonical_headers = "".join(f"{k}:{h[k]}\n" for k in sorted(h))
    query = "&".join(sorted(p for p in u.query.split("&") if p)) if u.query else ""
    canonical = "\n".join([method, quote(u.path or "/", safe="/-_.~"), query, canonical_headers, signed, payload_sha256])
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), date), region), service), "aws4_request")
    sig = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {k: v for k, v in h.items() if k != "host"}
    out["authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"
    return out


class ObjectStore:
    def __init__(self, endpoint: str, region: str, bucket: str, access_key: str, secret_key: str,
                 client: httpx.Client | None = None, check_egress: bool = True):
        if not all((endpoint, region, bucket, access_key, secret_key)):
            raise ObjectStoreError("object store is not configured")
        if check_egress:
            from app import netpolicy
            try:
                netpolicy.check_endpoint(endpoint)
            except netpolicy.EgressDenied as exc:
                raise ObjectStoreError(f"egress denied: {exc}") from exc
        self.endpoint, self.region, self.bucket = endpoint.rstrip("/"), region, bucket
        self._ak, self._sk = access_key, secret_key
        self.http = client or httpx.Client(timeout=120)

    @classmethod
    def from_env(cls, **kw) -> "ObjectStore":
        e = os.environ.get
        return cls(e("AAV_OBJECT_STORE_ENDPOINT", ""), e("AAV_OBJECT_STORE_REGION", ""),
                   e("AAV_OBJECT_STORE_BUCKET", ""), e("AAV_OBJECT_STORE_ACCESS_KEY", ""),
                   e("AAV_OBJECT_STORE_SECRET_KEY", ""), **kw)

    def _url(self, key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ObjectStoreError("invalid object key")
        return f"{self.endpoint}/{quote(self.bucket)}/{quote(key, safe='/-_.~')}"

    def _req(self, method: str, key: str, body: bytes = b"", extra: dict | None = None) -> httpx.Response:
        url = self._url(key)
        digest = hashlib.sha256(body).hexdigest() if body else EMPTY_SHA256
        headers = sign_v4(method=method, url=url, headers=extra or {}, payload_sha256=digest, access_key=self._ak,
                          secret_key=self._sk, region=self.region, now=datetime.now(timezone.utc))
        return self.http.request(method, url, content=body or None, headers=headers)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        r = self._req("PUT", key, data, {"content-type": content_type})
        if r.status_code not in (200, 201):
            raise ObjectStoreError(f"PUT {key}: HTTP {r.status_code} {r.text[:200]}")
        return {"key": key, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "etag": r.headers.get("etag")}

    def get(self, key: str) -> bytes:
        r = self._req("GET", key)
        if r.status_code != 200:
            raise ObjectStoreError(f"GET {key}: HTTP {r.status_code}")
        return r.content

    def exists(self, key: str) -> bool:
        return self._req("HEAD", key).status_code == 200

    def delete(self, key: str) -> None:
        r = self._req("DELETE", key)
        if r.status_code not in (200, 204, 404):
            raise ObjectStoreError(f"DELETE {key}: HTTP {r.status_code}")
