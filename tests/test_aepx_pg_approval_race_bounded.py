"""Static safety checks for bounded PostgreSQL concurrency harness."""
import unittest
from pathlib import Path
S=(Path(__file__).resolve().parents[1]/"scripts/test_aepx_pg_approval_concurrency.py").read_text()
class BoundedRaceTests(unittest.TestCase):
 def test_bounded_readiness_and_process_cleanup(self):
  for token in ("selectors.DefaultSelector","ready.select(timeout=10)",
                "FIRST_CONSUMED","for process in (second,first)",
                "process.kill()","process.wait(timeout=5)"):
   self.assertIn(token,S)
 def test_no_query_output_before_marker(self):
  self.assertIn("DO $consume$ BEGIN PERFORM",S)
  self.assertNotIn("consume=f\"SELECT",S)
 def test_disposable_guardrails_preserved(self):
  for token in ("aepx_test_","PGHOSTADDR","rolbypassrls","relforcerowsecurity"):
   self.assertIn(token,S)
if __name__=="__main__": unittest.main()
