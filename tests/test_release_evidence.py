import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from verify_release_evidence import assess
SHA="a"*40
def run(name,status="completed",conclusion="success",sha=SHA,event="push",number=1):
    return dict(name=name,status=status,conclusion=conclusion,headSha=sha,event=event,runNumber=number)
class ReleaseEvidenceTests(unittest.TestCase):
    def test_exact_sha_success(self):
        self.assertEqual(assess([run("CI"),run("HITL P0 acceptance")],SHA),[])
    def test_queued_blocks(self):
        self.assertTrue(assess([run("CI","queued",None),run("HITL P0 acceptance")],SHA))
    def test_missing_blocks(self):
        self.assertTrue(assess([run("CI")],SHA))
    def test_other_sha_does_not_count(self):
        self.assertTrue(assess([run("CI",sha="b"*40),run("HITL P0 acceptance")],SHA))
    def test_pull_request_event_does_not_count(self):
        self.assertTrue(assess([run("CI",event="pull_request"),run("HITL P0 acceptance")],SHA))
    def test_latest_failure_blocks(self):
        self.assertTrue(assess([run("CI",number=1),run("CI","completed","failure",number=2),
                                run("HITL P0 acceptance")],SHA))
if __name__=="__main__":
    unittest.main()
