import importlib.util
import pathlib
import tempfile
import unittest
p=pathlib.Path(__file__).resolve().parents[1]/"scripts/aepx-hitl-store.py"
spec=importlib.util.spec_from_file_location("aepx_hitl_store",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class HitlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.tmp.name)/"approvals.db"
        self.store=m.ApprovalStore(self.path)
        self.action={"tool":"write","resource":"invoice:1","amount":100}
    def tearDown(self):self.tmp.cleanup()
    def test_durable_approval_and_one_time_consume(self):
        aid=self.store.request(self.action,"requester",now=100)
        self.store.decide(aid,"reviewer",True,now=101)
        self.assertTrue(m.ApprovalStore(self.path).consume(aid,self.action,now=102))
        with self.assertRaises(m.ApprovalDenied):self.store.consume(aid,self.action,now=103)
        self.assertEqual([x[0] for x in self.store.events(aid)],["requested","approved","consumed"])
    def test_rejection(self):
        aid=self.store.request(self.action,"requester",now=100)
        self.store.decide(aid,"reviewer",False,now=101)
        with self.assertRaises(m.ApprovalDenied):self.store.consume(aid,self.action,now=102)
    def test_self_approval_denied(self):
        aid=self.store.request(self.action,"requester",now=100)
        with self.assertRaises(m.ApprovalDenied):self.store.decide(aid,"requester",True,now=101)
    def test_mismatched_action_denied(self):
        aid=self.store.request(self.action,"requester",now=100)
        self.store.decide(aid,"reviewer",True,now=101)
        with self.assertRaises(m.ApprovalDenied):
            self.store.consume(aid,{"tool":"write","resource":"invoice:1","amount":999},now=102)
    def test_expiry(self):
        aid=self.store.request(self.action,"requester",ttl_seconds=5,now=100)
        with self.assertRaises(m.ApprovalDenied):self.store.decide(aid,"reviewer",True,now=105)
    def test_pending_cannot_consume(self):
        aid=self.store.request(self.action,"requester",now=100)
        with self.assertRaises(m.ApprovalDenied):self.store.consume(aid,self.action,now=101)
if __name__=="__main__":unittest.main()
