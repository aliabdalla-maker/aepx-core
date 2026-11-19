"""Phase 2.7 deterministic network and crash-boundary security tests."""
import os
os.environ.setdefault("IDE_DATABASE_URL","postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER","https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL","https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE","ide-api")
import pytest
from app.egress27 import resolve_public,gateway_get,PinnedHTTPSConnection
from app.governed_worker import execute_next

def dns(ip):
    return lambda *args,**kwargs: [(2,1,6,"",(ip,443))]

@pytest.mark.parametrize("address",["127.0.0.1","10.0.0.1","169.254.169.254",
                                    "192.168.1.1","::1","fd00::1"])
def test_dns_rebinding_private_addresses_rejected(address):
    with pytest.raises(PermissionError):
        resolve_public("approved.example.test",resolver=dns(address))

def test_mixed_public_and_private_answers_fail_closed():
    def resolver(*args,**kwargs):
        return dns("8.8.8.8")()[0:1]+dns("127.0.0.1")()[0:1]
    with pytest.raises(PermissionError):
        resolve_public("approved.example.test",resolver=resolver)

def test_public_address_pinned_without_second_dns_resolution(monkeypatch):
    from unittest.mock import Mock
    import app.egress27 as module
    calls=[]
    def connect(target,timeout):
        calls.append(target)
        return Mock()
    monkeypatch.setattr(module.socket,"create_connection",connect)
    connection=PinnedHTTPSConnection("approved.example.test","8.8.8.8")
    connection._context=Mock()
    connection.connect()
    assert calls==[("8.8.8.8",443)]
    assert connection._context.wrap_socket.call_args.kwargs["server_hostname"]=="approved.example.test"

def test_gateway_never_attempts_connection_for_rebound_private_address(monkeypatch):
    import app.egress27 as module
    def forbidden(*args,**kwargs):
        raise AssertionError("network socket must never be opened")
    monkeypatch.setattr(module.socket,"create_connection",forbidden)
    with pytest.raises(PermissionError):
        gateway_get("https://approved.example.test/resource",
                    allowed_hosts={"approved.example.test"},resolver=dns("169.254.169.254"))

def test_gateway_rejects_redirect_candidate_and_nonstandard_port():
    with pytest.raises(PermissionError):
        gateway_get("https://approved.example.test:8443/",
                    allowed_hosts={"approved.example.test"})

def test_external_worker_remains_disabled(monkeypatch):
    monkeypatch.delenv("IDE_EXTERNAL_EXECUTION_ENABLED",raising=False)
    monkeypatch.setenv("IDE_GOVERNED_WORKER_ENABLED","true")
    with pytest.raises(PermissionError):
        execute_next("alpha")
