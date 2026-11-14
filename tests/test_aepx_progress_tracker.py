"""Offline tests for weighted evidence-gated progress."""
import unittest
from copy import deepcopy
from scripts.aepx_progress_tracker import WEIGHTS,calculate,ProgressDenied
def baseline():
 return {"schema_version":1,"milestones":{k:{"status":"not_started","evidence":[]} for k in WEIGHTS}}
class ProgressTrackerTests(unittest.TestCase):
 def test_zero_is_honest_default(self):
  self.assertEqual(calculate(baseline())["progress_percent"],0)
 def test_weighted_progress_not_magic_77(self):
  m=baseline()
  m["milestones"]["architecture"]={"status":"code_committed","evidence":["PR #1"]}
  self.assertEqual(calculate(m)["progress_percent"],2.5)
 def test_full_acceptance_is_100(self):
  m=baseline()
  for k in WEIGHTS:
   m["milestones"][k]={"status":"accepted","evidence":["reviewed evidence"]}
  self.assertEqual(calculate(m)["progress_percent"],100)
 def test_missing_evidence_denied(self):
  m=baseline()
  m["milestones"]["security"]["status"]="accepted"
  with self.assertRaises(ProgressDenied):calculate(m)
 def test_unknown_milestone_denied(self):
  m=baseline();m["milestones"]["extra"]={"status":"accepted","evidence":["x"]}
  with self.assertRaises(ProgressDenied):calculate(m)
 def test_bool_schema_denied(self):
  m=baseline();m["schema_version"]=True
  with self.assertRaises(ProgressDenied):calculate(m)
if __name__=="__main__":unittest.main()
