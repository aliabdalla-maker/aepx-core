"""Real PostgreSQL concurrent replay acceptance; requires HITL_REPLAY_TEST_DSN.

Runs against an isolated ephemeral database. No production database permitted.
"""
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_receipt_replay_postgres import postgres_receipt_claimer

@unittest.skipUnless(os.getenv("HITL_REPLAY_TEST_DSN"),"isolated PostgreSQL DSN required")
class ReplayConcurrencyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg
        cls.dsn=os.environ["HITL_REPLAY_TEST_DSN"]
        if os.getenv("HITL_REPLAY_ALLOW_ISOLATED_TEST")!="yes":
            raise RuntimeError("explicit isolated database test opt-in required")
        with psycopg.connect(cls.dsn) as conn:
            conn.execute("CREATE SCHEMA IF NOT EXISTS hitl")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.provider_receipt_claims (
                provider text NOT NULL, receipt_id text NOT NULL,
                claimed_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(provider,receipt_id))""")
    def test_concurrent_exactly_one_winner(self):
        from uuid import uuid4
        receipt="receipt-"+uuid4().hex
        claim=postgres_receipt_claimer(lambda:self.psycopg.connect(self.dsn,connect_timeout=3))
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes=list(pool.map(lambda _:claim(provider="provider-test",receipt_id=receipt),range(24)))
        self.assertEqual(outcomes.count(True),1)
        self.assertEqual(outcomes.count(False),23)
        with self.psycopg.connect(self.dsn) as conn:
            count=conn.execute("SELECT count(*) FROM hitl.provider_receipt_claims WHERE provider=%s AND receipt_id=%s",
                ("provider-test",receipt)).fetchone()[0]
        self.assertEqual(count,1)
    def test_separate_receipts_are_independent(self):
        from uuid import uuid4
        claim=postgres_receipt_claimer(lambda:self.psycopg.connect(self.dsn,connect_timeout=3))
        self.assertTrue(claim(provider="provider-test",receipt_id="receipt-"+uuid4().hex))
        self.assertTrue(claim(provider="provider-test",receipt_id="receipt-"+uuid4().hex))
if __name__=="__main__":
    unittest.main()
