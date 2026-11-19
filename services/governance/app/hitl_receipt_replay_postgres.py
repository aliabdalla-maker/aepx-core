"""Durable, atomic PostgreSQL replay-claim adapter for signed provider receipts.

The caller must supply a dedicated restricted DB connection. Claiming is
committed before a signed receipt can be returned as verified.
"""
import re

class ReplayClaimDenied(PermissionError):
    pass

_TOKEN=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")

def postgres_receipt_claimer(connection_factory):
    """Build claim_receipt_id callback for verify_signed_receipt.

    Each call opens its own transaction. A unique(provider,receipt_id)
    constraint is mandatory; a duplicate returns False. Any outage denies.
    """
    if not callable(connection_factory):
        raise ReplayClaimDenied("trusted connection factory required")

    def claim(*,provider,receipt_id):
        if (not isinstance(provider,str) or _TOKEN.fullmatch(provider) is None
            or not isinstance(receipt_id,str) or _TOKEN.fullmatch(receipt_id) is None):
            return False
        try:
            with connection_factory() as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO hitl.provider_receipt_claims
                        (provider,receipt_id) VALUES (%s,%s)
                        ON CONFLICT (provider,receipt_id) DO NOTHING
                        RETURNING receipt_id""",(provider,receipt_id))
                    row=cur.fetchone()
                if row is None:
                    conn.rollback()
                    return False
                conn.commit()
                return row[0]==receipt_id
        except Exception:
            return False
    return claim
