"""Regression: self-reported milestone status must not masquerade as verification."""
import unittest
from scripts.aepx_progress_tracker import WEIGHTS,calculate
class ProgressVerificationSeparationTests(unittest.TestCase):
 def test_self_reported_acceptance_is_not_verified(self):
  manifest={"schema_version":1,"milestones":{
   name:{"status":"accepted","evidence":["arbitrary claim"]}
   for name in WEIGHTS}}
  result=calculate(manifest)
  self.assertEqual(result["claimed_progress_percent"],100)
  self.assertEqual(result["independently_verified_percent"],0)
  self.assertEqual(result["verification"],"unverified_manifest_claims")
  self.assertIn("NOT verified",result["warning"])
 def test_committed_claim_also_not_verified(self):
  manifest={"schema_version":1,"milestones":{
   name:{"status":"not_started","evidence":[]} for name in WEIGHTS}}
  manifest["milestones"]["architecture"]={"status":"code_committed","evidence":["PR #342"]}
  result=calculate(manifest)
  self.assertEqual(result["claimed_progress_percent"],2.5)
  self.assertEqual(result["independently_verified_percent"],0)
if __name__=="__main__": unittest.main()
