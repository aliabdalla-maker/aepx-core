import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/governance"))
from app.hitl_tool_policy import guarded_adapter,ToolPolicyDenied

class ToolPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tenant=uuid4()
        self.action_hash="a"*64
        self.adapter=MagicMock()
        self.guard=guarded_adapter(self.adapter,allowed_tenants=[self.tenant],
                                   allowed_action_hashes=[self.action_hash])
        self.event=dict(event_id=str(uuid4()),topic="hitl.approval.consumed",
                        tenant_id=str(self.tenant),
                        payload=dict(approval_id=str(uuid4()),
                                     action_hash=self.action_hash,actor_id="worker"))
    def test_kill_switch_default_denies(self):
        with patch.dict(os.environ,{"HITL_EXTERNAL_EFFECTS_ENABLED":""}):
            with self.assertRaises(ToolPolicyDenied): self.guard(**self.event)
        self.adapter.assert_not_called()
    def test_allowlisted_event_can_reach_adapter_only_when_enabled(self):
        with patch.dict(os.environ,{"HITL_EXTERNAL_EFFECTS_ENABLED":"yes"}):
            self.guard(**self.event)
        self.adapter.assert_called_once()
    def test_cross_tenant_denied(self):
        with patch.dict(os.environ,{"HITL_EXTERNAL_EFFECTS_ENABLED":"yes"}):
            with self.assertRaises(ToolPolicyDenied):
                self.guard(**dict(self.event,tenant_id=str(uuid4())))
        self.adapter.assert_not_called()
    def test_unapproved_hash_denied(self):
        with patch.dict(os.environ,{"HITL_EXTERNAL_EFFECTS_ENABLED":"yes"}):
            with self.assertRaises(ToolPolicyDenied):
                self.guard(**dict(self.event,payload=dict(self.event["payload"],action_hash="b"*64)))
        self.adapter.assert_not_called()
    def test_malformed_payload_denied(self):
        with patch.dict(os.environ,{"HITL_EXTERNAL_EFFECTS_ENABLED":"yes"}):
            with self.assertRaises(ToolPolicyDenied):
                self.guard(**dict(self.event,payload={}))
        self.adapter.assert_not_called()
    def test_unapproved_topic_denied(self):
        with patch.dict(os.environ,{"HITL_EXTERNAL_EFFECTS_ENABLED":"yes"}):
            with self.assertRaises(ToolPolicyDenied):
                self.guard(**dict(self.event,topic="mcp.execute"))
        self.adapter.assert_not_called()
    def test_invalid_allowlist_denied(self):
        with self.assertRaises(ValueError):
            guarded_adapter(self.adapter,allowed_tenants=[self.tenant],allowed_action_hashes=[])
if __name__=="__main__": unittest.main()
