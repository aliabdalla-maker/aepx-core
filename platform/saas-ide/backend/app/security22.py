"""Network and budget policy primitives; not a substitute for container egress enforcement."""
import ipaddress
import math
from dataclasses import dataclass
from urllib.parse import urlsplit

def validate_public_ip(ip: str) -> str:
    addr=ipaddress.ip_address(ip)
    if not addr.is_global:
        raise ValueError("Non-public address denied")
    return str(addr)

def validate_endpoint(url: str) -> str:
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Invalid HTTPS endpoint")
    try:
        validate_public_ip(parsed.hostname)
    except ValueError:
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            if parsed.hostname in ("localhost",) or parsed.hostname.endswith((".local",".internal")):
                raise ValueError("Internal hostname denied")
        else:
            raise
    return url

@dataclass(frozen=True)
class Budget:
    max_tokens: int
    max_cost_usd: float
    timeout_seconds: int
    def __post_init__(self):
        if not 1<=self.max_tokens<=2000 or not math.isfinite(self.max_cost_usd) or not 0<self.max_cost_usd<=5 or not 1<=self.timeout_seconds<=60:
            raise ValueError("Budget outside approved limits")

def estimate_max_cost(budget: Budget, price_per_million_tokens: float) -> float:
    if not math.isfinite(price_per_million_tokens) or price_per_million_tokens<=0:
        raise ValueError("Pricing configuration required")
    estimate=budget.max_tokens*price_per_million_tokens/1_000_000
    if estimate>budget.max_cost_usd:
        raise PermissionError("Estimated model cost exceeds budget")
    return estimate
