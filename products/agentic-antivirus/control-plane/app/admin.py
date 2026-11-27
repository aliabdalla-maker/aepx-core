"""Operator commands, run inside the control-plane container by someone with server access:

    docker compose exec control-plane python -m app.admin verify-email someone@example.com
    docker compose exec control-plane python -m app.admin send-mail
    docker compose exec control-plane python -m app.admin publish-baseline
    docker compose exec -T control-plane python -m app.admin store-backup NAME < file   (BE-05, off-VM copy)
    docker compose exec -T control-plane python -m app.admin fetch-backup NAME > file

publish-baseline signs and publishes the shipped baseline detection rules (detection/rules/baseline.json) if no
detection bundle has been published yet, so newly enrolled devices can scan straight away. It never replaces a
published bundle and is safe to run on every install.

verify-email marks one existing account verified (for the operator's own first account, or when mail
delivery is down) and writes an audit record naming the operator CLI. It never creates accounts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app import audit, crypto, db, mailer

BASELINE = Path(__file__).resolve().parents[2] / "detection" / "rules" / "baseline.json"


def verify_email(email: str) -> int:
    with db.global_tx() as cur:
        cur.execute("UPDATE aav.users SET email_verified = true WHERE email = %s AND deleted_at IS NULL "
                    "RETURNING id", (email.lower(),))
        row = cur.fetchone()
        if not row:
            print(f"no account for {email}", file=sys.stderr)
            return 1
        audit.record(cur, tenant_id=None, actor="operator:cli", action="account.email_verified_by_operator",
                     target=str(row["id"]))
    print(f"verified {email}")
    return 0


def publish_baseline(path: Path = BASELINE) -> int:
    from app.detections import validate_bundle
    doc = json.loads(path.read_text(encoding="utf-8"))
    version, body = doc["version"], doc["body"]
    validate_bundle("detections", body)
    with db.global_tx() as cur:
        cur.execute("SELECT version FROM aav.update_bundles WHERE kind = 'detections' AND revoked_at IS NULL "
                    "ORDER BY published_at DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            print(f"detections {row['version']} already published; baseline not needed")
            return 0
        signed = {"kind": "detections", "version": version, "body": body}
        cur.execute("INSERT INTO aav.update_bundles (kind, version, body, signature, key_id, published_by) "
                    "VALUES ('detections', %s, %s, %s, %s, NULL) ON CONFLICT (kind, version) DO NOTHING RETURNING id",
                    (version, json.dumps(body), crypto.sign(signed), crypto.key_id()))
        row = cur.fetchone()
        if not row:  # this baseline version was published before and has since been revoked: respect that
            print(f"baseline detections {version} was revoked; publish a new version instead", file=sys.stderr)
            return 1
        audit.record(cur, tenant_id=None, actor="operator:cli", action="update.publish_baseline",
                     target=str(row["id"]), detail={"kind": "detections", "version": version})
    print(f"published baseline detections {version}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "verify-email":
        return verify_email(argv[1])
    if argv == ["retention"]:
        from app import db
        with db.global_tx() as cur:
            cur.execute("SELECT aav.apply_telemetry_retention() AS n")
            print(f"deleted {cur.fetchone()['n']} expired telemetry events")
        return 0
    if len(argv) == 2 and argv[0] in ("store-backup", "fetch-backup"):
        from app.objectstore import ObjectStore, ObjectStoreError
        name = Path(argv[1]).name
        try:
            store = ObjectStore.from_env()
            if argv[0] == "store-backup":
                print(json.dumps(store.put(f"backups/{name}", sys.stdin.buffer.read())))
            else:
                sys.stdout.buffer.write(store.get(f"backups/{name}"))
        except ObjectStoreError as exc:
            print(f"object store: {exc}", file=sys.stderr)
            return 1
        return 0
    if argv == ["publish-baseline"]:
        return publish_baseline()
    if argv == ["send-mail"]:
        print(mailer.deliver_pending())
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
