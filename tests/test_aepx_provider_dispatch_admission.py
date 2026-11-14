"""Offline provider dispatch admission regression tests."""
import unittest
from scripts.aepx_provider_dispatch_admission import authorize_first_dispatch, DispatchDenied

VALID=dict(reservation_status="reserved",approval_verified=True,lease_fence=1,
           idempotency_key="provider_request_0001",tenant_id="tenant-1",
           request_id="req-1",budget_committed=True,worker_isolated=True)

class DispatchAdmissionTests(unittest.TestCase):
    def test_valid_inputs_are_only_eligible(self):
        result=authorize_first_dispatch(**VALID)
        self.assertEqual(result["decision"],"eligible_for_fenced_dispatch")

    def test_reservation_replays_never_dispatch(self):
        for status in ("already_reserved","already_settled",None,"failed","reserved "):
            with self.subTest(status=status),self.assertRaises(DispatchDenied):
                authorize_first_dispatch(**{**VALID,"reservation_status":status})

    def test_fail_closed_for_missing_guards(self):
        cases={"approval_verified":False,"lease_fence":0,
               "idempotency_key":"short","tenant_id":"",
               "request_id":"bad/request","budget_committed":False,
               "worker_isolated":False}
        for key,value in cases.items():
            with self.subTest(key=key),self.assertRaises(DispatchDenied):
                authorize_first_dispatch(**{**VALID,key:value})

    def test_bool_fence_and_truthy_nonboolean_denied(self):
        for key,value in (("lease_fence",True),("approval_verified",1),
                          ("budget_committed","yes"),("worker_isolated",1)):
            with self.subTest(key=key),self.assertRaises(DispatchDenied):
                authorize_first_dispatch(**{**VALID,key:value})

if __name__=="__main__":
    unittest.main()
