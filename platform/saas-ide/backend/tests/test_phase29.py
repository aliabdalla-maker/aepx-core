"""Offline security tests; never enable live provider execution."""
import os
import signal
import subprocess
import sys
import time
import pytest
from app.billing29 import canonical_receipt,sign_mock_receipt,verify_mock_receipt,reconcile_mock_receipt
from app.egress27 import resolve_public

KEY=b"mock-test-only-key-32-bytes-minimum!!!!"
RECEIPT={"tenant":"alpha","reservation":"res-1","provider":"mock",
         "request_id":"req-1","tokens":37,"microusd":2000}

def test_mock_receipt_tampering_and_type_confusion():
    signature=sign_mock_receipt(RECEIPT,KEY)
    verify_mock_receipt(RECEIPT,signature,KEY)
    for field,value in (("tenant","beta"),("tokens",38),("microusd",2001),("request_id","req-2")):
        modified=dict(RECEIPT,**{field:value})
        with pytest.raises(PermissionError):
            verify_mock_receipt(modified,signature,KEY)
    with pytest.raises(ValueError):
        canonical_receipt(dict(RECEIPT,tokens=True))
    with pytest.raises(PermissionError):
        verify_mock_receipt(RECEIPT,signature,b"short")

def test_mock_receipt_tenant_denial_before_database_use():
    class NeverDB:
        def execute(self,*args,**kwargs):
            raise AssertionError("Database should not be reached")
    with pytest.raises(PermissionError):
        reconcile_mock_receipt(NeverDB(),"beta",RECEIPT,
                               sign_mock_receipt(RECEIPT,KEY),KEY,actor="test")

@pytest.mark.skipif(sys.platform=="win32",reason="SIGKILL is POSIX-specific")
def test_real_sigkill_subprocess_cannot_commit_after_termination(tmp_path):
    """Real OS SIGKILL; isolated process has no DB credentials or provider keys."""
    marker=tmp_path/"should-not-exist"
    code="import time,pathlib;time.sleep(10);pathlib.Path(%r).write_text('committed')" % str(marker)
    proc=subprocess.Popen([sys.executable,"-c",code],
                          env={"PATH":os.getenv("PATH",""),"PYTHONUNBUFFERED":"1"},
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        time.sleep(.1)
        assert proc.poll() is None
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)
        assert proc.returncode!=0
        assert not marker.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

def test_dns_metadata_and_private_rebinding_denied():
    for address in ("169.254.169.254","127.0.0.1","10.0.0.3","::1"):
        with pytest.raises(PermissionError):
            resolve_public("provider.example.test",resolver=lambda *a,ip=address,**kw:
                           [(2,1,6,"",(ip,443))])
