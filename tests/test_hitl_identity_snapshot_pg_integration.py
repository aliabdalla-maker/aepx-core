"""Isolated PostgreSQL acceptance for atomic identity snapshot revisions."""
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_snapshot import publish_identity_snapshot,SnapshotRejected

@unittest.skipUnless(os.getenv("HITL_IDENTITY_TEST_DSN") and
                     os.getenv("HITL_IDENTITY_TEST_ISOLATED")=="yes",
                     "explicit isolated PostgreSQL test opt-in required")
class SnapshotPgAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg
        cls.dsn=os.environ["HITL_IDENTITY_TEST_DSN"]
        # Validate the actual connected database before any DDL or writes.
        # An opt-in environment flag alone is not a production safety barrier.
        with psycopg.connect(cls.dsn,connect_timeout=5) as conn:
            actual_db=conn.execute("SELECT current_database()").fetchone()[0]
            if actual_db != "identity_test":
                raise RuntimeError("isolated test database identity_test required")
            conn.execute("CREATE SCHEMA IF NOT EXISTS hitl")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.identity_authority_sync (
                tenant_id uuid NOT NULL, issuer text NOT NULL,
                synced_at timestamptz NOT NULL, healthy boolean NOT NULL DEFAULT false,
                revision bigint NOT NULL DEFAULT 0,
                PRIMARY KEY (tenant_id,issuer))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.identity_memberships (
                tenant_id uuid NOT NULL,subject text NOT NULL,issuer text NOT NULL,
                active boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(tenant_id,subject,issuer))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.identity_revocations (
                tenant_id uuid NOT NULL,subject text NOT NULL,issuer text NOT NULL,
                token_id text NOT NULL,revoked_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(tenant_id,subject,issuer,token_id))""")
    def test_concurrent_revision_one_winner_and_consistent_rows(self):
        tenant=str(uuid4())
        issuer="https://identity.example"
        def publish(revision,member):
            with self.psycopg.connect(self.dsn,connect_timeout=5) as conn:
                try:
                    return publish_identity_snapshot(conn,tenant_id=tenant,issuer=issuer,
                        memberships=[member],revoked_tokens=[(member,"revoked-"+str(revision))],
                        captured_at=datetime.now(timezone.utc),revision=revision)
                except SnapshotRejected:
                    return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda item:publish(*item),
                [(1,"member-00001"),(1,"member-00002")]))
        self.assertEqual(results.count(True),1)
        self.assertEqual(results.count(False),1)
        with self.psycopg.connect(self.dsn) as conn:
            revision=conn.execute("""SELECT revision FROM hitl.identity_authority_sync
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer)).fetchone()[0]
            members=conn.execute("""SELECT subject FROM hitl.identity_memberships
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer)).fetchall()
            revocations=conn.execute("""SELECT subject FROM hitl.identity_revocations
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer)).fetchall()
        self.assertEqual(revision,1)
        self.assertEqual(len(members),1)
        self.assertEqual(revocations,members)
        self.assertFalse(publish(1,"member-00003"))
        self.assertTrue(publish(2,"member-00004"))
        with self.psycopg.connect(self.dsn) as conn:
            self.assertEqual(conn.execute("""SELECT revision FROM hitl.identity_authority_sync
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer)).fetchone()[0],2)
            self.assertEqual(conn.execute("""SELECT subject FROM hitl.identity_memberships
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer)).fetchone()[0],"member-00004")
if __name__=="__main__":
    unittest.main()
