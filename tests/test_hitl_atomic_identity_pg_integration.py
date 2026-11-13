"""Real PostgreSQL acceptance for single-statement identity decisions.

Requires explicit opt-in and local identity_test; never touches production.
"""
import os
import sys
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_identity_postgres import enforce_postgres_identity
from app.hitl_identity_policy import IdentityPolicyDenied

@unittest.skipUnless(os.getenv("HITL_IDENTITY_TEST_ISOLATED")=="yes" and
                     os.getenv("HITL_IDENTITY_TEST_DSN"),
                     "isolated PostgreSQL acceptance opt-in required")
class AtomicIdentityPgAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg=psycopg
        cls.dsn=os.environ["HITL_IDENTITY_TEST_DSN"]
        with psycopg.connect(cls.dsn,connect_timeout=5) as conn:
            if (conn.info.host not in ("localhost","127.0.0.1","::1")
                or conn.execute("SELECT current_database()").fetchone()[0]!="identity_test"):
                raise RuntimeError("local identity_test database required")
            conn.execute("CREATE SCHEMA IF NOT EXISTS hitl")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.identity_authority_sync (
                tenant_id uuid NOT NULL,issuer text NOT NULL,synced_at timestamptz NOT NULL,
                healthy boolean NOT NULL DEFAULT false,revision bigint NOT NULL DEFAULT 0,
                PRIMARY KEY(tenant_id,issuer))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.identity_memberships (
                tenant_id uuid NOT NULL,subject text NOT NULL,issuer text NOT NULL,
                active boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(tenant_id,subject,issuer))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS hitl.identity_revocations (
                tenant_id uuid NOT NULL,subject text NOT NULL,issuer text NOT NULL,
                token_id text NOT NULL,revoked_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY(tenant_id,subject,issuer,token_id))""")
    def test_membership_revocation_freshness_and_tenant_isolation(self):
        tenant=str(uuid4())
        other=str(uuid4())
        subject="subject-12345"
        token="token-12345"
        issuer="https://identity.example"
        def check(scope=tenant):
            return enforce_postgres_identity(
                connection_factory=lambda:self.psycopg.connect(self.dsn,connect_timeout=5),
                subject=subject,tenant_id=scope,token_id=token,issuer=issuer)
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute("""INSERT INTO hitl.identity_authority_sync
                (tenant_id,issuer,synced_at,healthy,revision)
                VALUES (%s,%s,now(),true,1)""",(tenant,issuer))
            conn.execute("""INSERT INTO hitl.identity_memberships
                (tenant_id,subject,issuer,active)
                VALUES (%s,%s,%s,true)""",(tenant,subject,issuer))
        self.assertTrue(check())
        with self.assertRaises(IdentityPolicyDenied):
            check(other)
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute("""INSERT INTO hitl.identity_revocations
                (tenant_id,subject,issuer,token_id)
                VALUES (%s,%s,%s,%s)""",(tenant,subject,issuer,token))
        with self.assertRaises(IdentityPolicyDenied):
            check()
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute("""DELETE FROM hitl.identity_revocations
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer))
            conn.execute("""UPDATE hitl.identity_authority_sync
                SET synced_at=now()-interval '120 seconds'
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer))
        with self.assertRaises(IdentityPolicyDenied):
            check()
        with self.psycopg.connect(self.dsn) as conn:
            conn.execute("""UPDATE hitl.identity_authority_sync
                SET synced_at=now(),healthy=false
                WHERE tenant_id=%s AND issuer=%s""",(tenant,issuer))
        with self.assertRaises(IdentityPolicyDenied):
            check()
if __name__=="__main__":
    unittest.main()
