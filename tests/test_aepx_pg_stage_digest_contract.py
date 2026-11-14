"""PostgreSQL iteration stage digest format contract."""
import re
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"platform/saas-ide/backend/sql/aepx_iteration_fenced.sql").read_text()
ACCEPTANCE=(ROOT/"tests/sql/aepx_iteration_pg_acceptance.sql").read_text()

class StageEvidenceDigestTests(unittest.TestCase):
    def test_canonical_digest_enforced_before_mutation(self):
        advance=SQL.split("CREATE OR REPLACE FUNCTION aepx_iteration.advance(",1)[1].split("END $$;",1)[0]
        self.assertIn("p_evidence !~ '^sha256:[0-9a-f]{64}$'",advance)
        self.assertIn("invalid stage evidence digest",advance)
        self.assertLess(advance.index("invalid stage evidence digest"),advance.index("UPDATE aepx_iteration.work_item"))
    def test_acceptance_rejects_malformed_digest(self):
        self.assertIn("sha256:malformed",ACCEPTANCE)
        self.assertIn("malformed evidence unexpectedly accepted",ACCEPTANCE)
        self.assertIn("invalid stage evidence digest",ACCEPTANCE)
    def test_all_fixture_valid_digests_are_canonical(self):
        values=re.findall(r"sha256:([a-zA-Z0-9]+)",ACCEPTANCE)
        self.assertGreaterEqual(len(values),6)
        for value in values:
            if value=="malformed": continue
            self.assertRegex(value,r"^[0-9a-f]{64}$")
if __name__=="__main__": unittest.main()
