"""Backup verification (REC-01): an S3-compatible bucket (AWS S3, OCI Object Storage, Backblaze B2, Wasabi, MinIO)
where the customer's backup tool writes. verify_backup checks that the newest object under config.prefix is newer
than config.max_age_hours (default 26) and not empty, and returns that object as evidence.
Credential "ACCESS_KEY:SECRET_KEY" (read-only key recommended); config {endpoint, region, bucket, prefix}.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.objectstore import ObjectStore, ObjectStoreError
from app.providers.base import Provider, ProviderError


class S3Backup(Provider):
    kind, name = "backup", "s3"

    def __init__(self, config, secret, **kw):
        super().__init__(config, secret, endpoint=(config or {}).get("endpoint", ""), **kw)
        ak, _, sk = self.secret.partition(":")
        try:
            self.store = ObjectStore(self.endpoint, self.config.get("region", ""), self.config.get("bucket", ""), ak, sk,
                                     client=self.http, check_egress=False)   # egress already checked by Provider
        except ObjectStoreError as exc:
            raise ProviderError(f"needs config endpoint/region/bucket and 'ACCESS:SECRET': {exc}") from exc

    def health(self) -> dict:
        try:
            n = len(self.store.list(self.config.get("prefix", ""), max_keys=1))
        except ObjectStoreError as exc:
            raise ProviderError(str(exc)) from exc
        return {"ok": True, "detail": f"bucket readable ({n} object(s) sampled)"}

    def verify_backup(self, item_id) -> dict:
        now = datetime.now(timezone.utc)
        max_age = float(self.config.get("max_age_hours", 26))
        try:
            objs = [o for o in self.store.list(self.config.get("prefix", "")) if o["size"] > 0]
        except ObjectStoreError as exc:
            return {"verified": False, "reason": str(exc), "checked_at": now.isoformat(), "provider": self.name}
        if not objs:
            return {"verified": False, "reason": "no non-empty backup objects under the prefix",
                    "checked_at": now.isoformat(), "provider": self.name}
        newest = max(objs, key=lambda o: o["last_modified"])
        age_h = (now - newest["last_modified"]).total_seconds() / 3600
        return {"verified": age_h <= max_age, "reason": None if age_h <= max_age else f"newest backup is {age_h:.1f} h old",
                "object": newest["key"], "size_bytes": newest["size"], "age_hours": round(age_h, 2),
                "max_age_hours": max_age, "checked_at": now.isoformat(), "provider": self.name, "item": str(item_id)}
