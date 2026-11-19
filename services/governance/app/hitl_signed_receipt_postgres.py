"""Signed receipt verification wired to durable PostgreSQL replay claims.

This is a pure adapter; callers must supply a restricted PostgreSQL
connection factory and a provider-specific secret from a trusted secret store.
"""
from .hitl_signed_receipts import verify_signed_receipt
from .hitl_receipt_replay_postgres import postgres_receipt_claimer

def verify_receipt_with_postgres(*,raw_body,signature,secret,expected_provider,
                                 connection_factory,now_epoch=None,
                                 max_age_seconds=300):
    claim=postgres_receipt_claimer(connection_factory)
    return verify_signed_receipt(
        raw_body=raw_body,signature=signature,secret=secret,
        expected_provider=expected_provider,now_epoch=now_epoch,
        max_age_seconds=max_age_seconds,claim_receipt_id=claim)
