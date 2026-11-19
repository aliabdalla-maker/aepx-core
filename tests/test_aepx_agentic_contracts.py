import importlib.util
import pathlib
import unittest
p=pathlib.Path(__file__).resolve().parents[1]/"scripts/aepx-agentic-contracts.py"
spec=importlib.util.spec_from_file_location("aepx_agentic_contracts",p)
m=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=m
spec.loader.exec_module(m)

class Contracts(unittest.TestCase):
    def test_tool_allowlist(self):
        policy=m.ToolPolicy("lookup",frozenset({"reader"}),5)
        self.assertTrue(m.authorize_tool(policy,tool="lookup",role="reader",timeout_seconds=3)["authorised"])
        for args in ({"tool":"write","role":"reader","timeout_seconds":3},
                     {"tool":"lookup","role":"admin","timeout_seconds":3},
                     {"tool":"lookup","role":"reader","timeout_seconds":8}):
            with self.assertRaises(m.Denied):m.authorize_tool(policy,**args)
    def test_tool_requires_approval(self):
        policy=m.ToolPolicy("update",frozenset({"operator"}),5,True)
        with self.assertRaises(m.Denied):
            m.authorize_tool(policy,tool="update",role="operator",timeout_seconds=2)
    def test_retrieval_provenance(self):
        result=m.grounded_answer("from document",["doc1"],[{"id":"doc1","content":"source text"}])
        self.assertEqual(result["grounding_status"],"source_ids_checked_only")
        with self.assertRaises(m.Denied):
            m.grounded_answer("fabricated",["missing"],[{"id":"doc1","content":"source text"}])
    def test_approval_bound_to_action(self):
        action={"tool":"update","amount":10}
        approval={"status":"approved","approver_id":"person1","action_hash":m.approval_fingerprint(action),"expires_at":200}
        self.assertTrue(m.check_approval(action,approval,now=100)["authorised"])
        with self.assertRaises(m.Denied):m.check_approval({"tool":"update","amount":100},approval,now=100)
        with self.assertRaises(m.Denied):m.check_approval(action,approval,now=201)
        with self.assertRaises(m.Denied):m.check_approval(action,{**approval,"consumed":True},now=100)
if __name__=="__main__":unittest.main()
