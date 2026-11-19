"""Workflow security contract tests; run after installing workflow requirements."""
import importlib.util
import pathlib
import unittest
from fastapi import HTTPException
from pydantic import ValidationError
from unittest.mock import AsyncMock, patch

path=pathlib.Path(__file__).resolve().parents[1]/"services/workflow/app/main.py"
spec=importlib.util.spec_from_file_location("aepx_workflow",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class WorkflowGuards(unittest.IsolatedAsyncioTestCase):
    def setUp(self): module._WORKFLOWS.clear()
    def test_reject_high_risk(self):
        with self.assertRaises(HTTPException) as cm:
            module.create_workflow(module.WorkflowIn(name="danger",steps=[{"capability":"write","agent_id":"a","risk_level":"S4"}]))
        self.assertEqual(cm.exception.status_code,403)
    def test_reject_empty_workflow(self):
        with self.assertRaises(ValidationError):
            module.WorkflowIn(name="empty",steps=[])
    async def test_unknown_workflow_404(self):
        with self.assertRaises(HTTPException) as cm:
            await module.execute_workflow("missing")
        self.assertEqual(cm.exception.status_code,404)
    async def test_duplicate_execution_rejected(self):
        w=module.create_workflow(module.WorkflowIn(name="read",steps=[{"capability":"lookup","agent_id":"a"}]))
        module._WORKFLOWS[w["id"]]["status"]="COMPLETED"
        with self.assertRaises(HTTPException) as cm:
            await module.execute_workflow(w["id"])
        self.assertEqual(cm.exception.status_code,409)
    async def test_registry_failure_marks_failed(self):
        w=module.create_workflow(module.WorkflowIn(name="read",steps=[{"capability":"lookup","agent_id":"a"}]))
        import httpx
        class Client:
            async def __aenter__(self): return self
            async def __aexit__(self,*args): return False
            async def get(self,*args): raise httpx.ConnectError("unavailable")
        with patch.object(module.httpx,"AsyncClient",return_value=Client()):
            with self.assertRaises(HTTPException) as cm:
                await module.execute_workflow(w["id"])
        self.assertEqual(cm.exception.status_code,502)
        self.assertEqual(module._WORKFLOWS[w["id"]]["status"],"FAILED")

if __name__=="__main__":unittest.main()
