"""Operator commands, run inside the control-plane container by someone with server access:

    docker compose exec control-plane python -m app.admin verify-email someone@example.com
    docker compose exec control-plane python -m app.admin send-mail

verify-email marks one existing account verified (for the operator's own first account, or when mail
delivery is down) and writes an audit record naming the operator CLI. It never creates accounts.
"""
from __future__ import annotations

import sys

from app import audit, db, mailer


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


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "verify-email":
        return verify_email(argv[1])
    if argv == ["send-mail"]:
        print(mailer.deliver_pending())
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
