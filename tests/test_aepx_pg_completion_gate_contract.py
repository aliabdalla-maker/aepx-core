"""Fail-closed SQL completion gate regression contract."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"platform/saas-ide/backend/sql/aepx_iteration_fenced.sql").read_text()
ACCEPTANCE=(ROOT/"tests/sql/aepx_iteration_pg_acceptance.sql").read_text()

class CompletionGateTests(unittest.TestCase):
    def test_completion_denied_after_stage_order_check(self):
        advance=SQL.split("CREATE OR REPLACE FUNCTION aepx_iteration.advance(",1)[1].split("END $$;",1)[0]
        self.assertIn("IF p_stage = 'completed' THEN",advance)
        self.assertIn("iteration completion requires trusted evidence and approval gate",advance)
        self.assertLess(advance.index("out-of-order iteration transition"),
                        advance.index("IF p_stage = 'completed' THEN"))
        self.assertLess(advance.index("IF p_stage = 'completed' THEN"),
                        advance.index("UPDATE aepx_iteration.work_item"))
    def test_runtime_acceptance_rejects_unverified_completion(self):
        self.assertIn("'completed','sha256:8888888888888888888888888888888888888888888888888888888888888888'",ACCEPTANCE)
        self.assertIn("unverified completion unexpectedly accepted",ACCEPTANCE)
        self.assertIn("denied completion mutated stage",ACCEPTANCE)
if __name__=="__main__": unittest.main()
