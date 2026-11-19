"""Static safety checks for opt-in two-connection PostgreSQL race harness."""
import unittest
from pathlib import Path
P=Path(__file__).resolve().parents[1]/"scripts/test_aepx_pg_approval_concurrency.py"
S=P.read_text()
class ApprovalRaceContract(unittest.TestCase):
 def test_local_disposable_guardrails(self):
  for token in ("aepx_test_","127.0.0.1","PGHOSTADDR","PGSERVICE",
                "rolbypassrls","relforcerowsecurity","--execute"):
   self.assertIn(token,S)
 def test_two_sessions_and_replay_denial(self):
  for token in ("subprocess.Popen","first.stdin.write","second.communicate",
                "COMMIT;","approval missing expired mismatched or consumed",
                "consumed_at IS NOT NULL","finally:"):
   self.assertIn(token,S)
 def test_fixture_is_atomic_and_cleaned(self):
  self.assertIn('setup=(scope+preflight+"BEGIN;"',S)
  self.assertIn('setup += "COMMIT;"',S)
  self.assertIn("run(cleanup)",S)
if __name__=="__main__": unittest.main()
