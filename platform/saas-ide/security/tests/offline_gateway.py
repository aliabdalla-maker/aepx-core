"""TEST ONLY: route one synthetic hostname to a local mock TLS service.

Production gateway remains untouched. The fixture overrides only the test
destination resolver and test upstream port, and runs solely in CI Compose.
"""
import importlib.util
import os
import socket

spec=importlib.util.spec_from_file_location("gateway","/opt/gateway/egress_gateway.py")
gateway=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
real_connect=socket.create_connection

def test_destination(authority, hosts, resolver=socket.getaddrinfo):
    print("TEST destination",repr(authority),repr(hosts),flush=True)
    if authority!="provider.example:443" or hosts!={"provider.example"}:
        raise PermissionError("Test-only allowlist violation")
    ip=socket.gethostbyname("mock-provider")
    print("TEST resolved mock provider",ip,flush=True)
    return ip

def connect(address, timeout=None, source_address=None, **kwargs):
    print("TEST connect",repr(address),flush=True)
    if address[1]==443 and address[0]==socket.gethostbyname("mock-provider"):
        return real_connect(("mock-provider",8443),timeout,source_address,**kwargs)
    return real_connect(address,timeout,source_address,**kwargs)

gateway.permitted_destination=test_destination
gateway.socket.create_connection=connect
os.environ["IDE_GATEWAY_ALLOWED_HOSTS"]="provider.example"
os.environ["IDE_GATEWAY_FORWARD_ENABLED"]="true"
os.environ["IDE_GATEWAY_TOKEN"]="offline-integration-token-1234567890"
with gateway.TLSServer(("0.0.0.0",8080),gateway.Handler,gateway.gateway_tls_context()) as server:
    server.serve_forever()
