import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_actions_queue import inspect_runs

class FakeResponse:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,*args): return self.payload
    def __init__(self,payload): self.payload=json.dumps(payload).encode()

class QueueAuditTests(unittest.TestCase):
    def test_queued_and_completed_distinguished(self):
        payload={"total_count":2,"workflow_runs":[
            {"id":1,"status":"queued","name":"CI","created_at":"2020-01-01T00:00:00Z"},
            {"id":2,"status":"completed","conclusion":"success"}]}
        with patch("audit_actions_queue.urllib.request.urlopen",
                   return_value=FakeResponse(payload)):
            result=inspect_runs("owner/repo")
        self.assertEqual(result["status_counts"],{"queued":1,"completed":1})
        self.assertEqual(result["queued_over_30_minutes"][0]["id"],1)
        self.assertEqual(result["sample_size"],2)
    def test_bad_repo_rejected(self):
        with self.assertRaises(ValueError): inspect_runs("invalid")
if __name__=="__main__":
    unittest.main()
