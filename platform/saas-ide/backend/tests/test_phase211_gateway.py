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
