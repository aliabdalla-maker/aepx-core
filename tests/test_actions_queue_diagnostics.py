import sys
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from diagnose_actions_queue import diagnose

NOW=datetime(2026,11,13,tzinfo=timezone.utc)
def sample(minutes,stamp=True):
    return {"id":12,"name":"HITL P0 acceptance","status":"queued",
            "created_at":(NOW-timedelta(minutes=minutes)).isoformat() if stamp else None}
JOBS={12:[{"name":"offline","status":"queued"},{"name":"postgres","status":"queued"}]}
class ActionsQueueTests(unittest.TestCase):
    def test_stale_queue_reports_both_jobs(self):
        findings=diagnose([sample(60)],JOBS,NOW)
        self.assertTrue(findings[0]["stale"])
        self.assertEqual(findings[0]["queued_jobs"],["offline","postgres"])
    def test_recent_queue_not_stale(self):
        self.assertFalse(diagnose([sample(2)],JOBS,NOW)[0]["stale"])
    def test_missing_timestamp_fails_closed(self):
        self.assertTrue(diagnose([sample(1,False)],JOBS,NOW)[0]["stale"])
    def test_completed_jobs_not_reported_as_queued(self):
        self.assertEqual(diagnose([sample(60)],{12:[{"name":"offline","status":"completed"}]},NOW),[])
if __name__=="__main__":
    unittest.main()
