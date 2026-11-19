import importlib.util
import pathlib
import unittest
from unittest.mock import patch
p=pathlib.Path(__file__).resolve().parents[1]/"scripts/aepx-agentic-acceptance.py"
spec=importlib.util.spec_from_file_location("aepx_agentic_acceptance",p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class AgenticAcceptanceTests(unittest.TestCase):
    def test_expected_policy_and_negative_paths(self):
        def fake_call(base,path,method="GET",body=None):
            if "policy/evaluate" in path:
                if "S0" in path:return 200,{"allowed":True}
                return 200,{"allowed":False}
            if "knowledge/search" in path:return 200,{"results":[]}
            return 404,{"detail":"not found"}
        with patch.object(module,"call",side_effect=fake_call):
            results=module.run({"governance":"x","knowledge":"y","workflow":"z"})
        self.assertEqual(len(results),5)
        self.assertTrue(all(x["passed"] for x in results))
    def test_policy_fail_open_detected(self):
        def fake_call(base,path,method="GET",body=None):
            if "policy/evaluate" in path:return 200,{"allowed":True}
            if "knowledge/search" in path:return 200,{"results":[]}
            return 404,{}
        with patch.object(module,"call",side_effect=fake_call):
            results=module.run({"governance":"x","knowledge":"y","workflow":"z"})
        self.assertFalse(next(x for x in results if x["check"]=="governance_S4")["passed"])
    def test_hallucinated_retrieval_detected(self):
        def fake_call(base,path,method="GET",body=None):
            if "policy/evaluate" in path:return 200,{"allowed":"S0" in path}
            if "knowledge/search" in path:return 200,{"results":[{"source":"invented"}]}
            return 404,{}
        with patch.object(module,"call",side_effect=fake_call):
            results=module.run({"governance":"x","knowledge":"y","workflow":"z"})
        self.assertFalse(next(x for x in results if x["check"]=="rag_negative_retrieval")["passed"])
if __name__=="__main__":unittest.main()
