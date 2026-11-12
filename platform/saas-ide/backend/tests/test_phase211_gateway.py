"""No outbound network required: adversarial CONNECT policy regressions."""
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[2]/"security"/"egress_gateway.py"
spec=importlib.util.spec_from_file_location("phase211_gateway",path)
gateway=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

def resolver(ip):
    return lambda *a,**kw:[(2,1,6,"",(ip,443))]

@pytest.mark.parametrize("authority",[
    "169.254.169.254:443","localhost:443","provider.example:80",
    "provider.example:8443","provider.example.:443","provider.example.evil:443",
    "PROVIDER.EXAMPLE:443","provider.example:443:443","provider..example:443",
])
def test_gateway_rejects_bypass(authority):
    with pytest.raises(PermissionError):
        gateway.permitted_destination(authority,{"provider.example"},resolver("8.8.8.8"))

@pytest.mark.parametrize("ip",["127.0.0.1","10.0.0.1","169.254.169.254","::1"])
def test_gateway_rejects_dns_rebinding(ip):
    with pytest.raises(PermissionError):
        gateway.permitted_destination("provider.example:443",{"provider.example"},resolver(ip))

def test_gateway_pins_public_dns():
    assert gateway.permitted_destination("provider.example:443",{"provider.example"},
                                        resolver("8.8.8.8"))=="8.8.8.8"

def test_gateway_rejects_mixed_dns():
    def mixed(*a,**kw):
        return resolver("8.8.8.8")(*a,**kw)+resolver("10.1.2.3")(*a,**kw)
    with pytest.raises(PermissionError):
        gateway.permitted_destination("provider.example:443",{"provider.example"},mixed)

@pytest.mark.parametrize("ip",[
    "0.0.0.0","100.64.0.1","172.16.0.1","192.168.1.1",
    "192.0.2.1","198.51.100.1","203.0.113.1",
    "224.0.0.1","255.255.255.255","fe80::1","fc00::1",
])
def test_gateway_rejects_non_global_dns_answers(ip):
    with pytest.raises(PermissionError):
        gateway.permitted_destination("provider.example:443",{"provider.example"},resolver(ip))

def test_gateway_rejects_empty_dns_answer():
    with pytest.raises(PermissionError):
        gateway.permitted_destination("provider.example:443",{"provider.example"},lambda *a,**kw:[])

def test_gateway_rejects_dns_rebinding_with_duplicate_private_and_public_records():
    def answers(*a,**kw):
        return resolver("8.8.8.8")(*a,**kw)+resolver("169.254.169.254")(*a,**kw)
    with pytest.raises(PermissionError):
        gateway.permitted_destination("provider.example:443",{"provider.example"},answers)

@pytest.mark.parametrize("authority",[
    "provider.example:443/","provider.example:443@evil.example",
    "provider.example:0443","provider.example:443\\r\\nHost: evil.example",
    "[::1]:443","provider.example:443#fragment",
])
def test_gateway_rejects_connect_authority_smuggling(authority):
    with pytest.raises(PermissionError):
        gateway.permitted_destination(authority,{"provider.example"},resolver("8.8.8.8"))
