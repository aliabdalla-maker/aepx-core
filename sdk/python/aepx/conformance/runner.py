"""Conformance runner — executes the check registry against a live
deployment via an AepxClient and aggregates a report (RFC-0007)."""
import time
from dataclasses import dataclass, asdict, field

from aepx.conformance.checks import CHECKS, PASS, FAIL, SKIP


@dataclass
class ConformanceReport:
    target: dict
    results: list = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0

    @property
    def conformant(self) -> bool:
        # Skips don't count against conformance — an unreachable subsystem
        # is a deployment state, not a protocol violation. Zero passes is
        # still non-conformant: proving nothing proves nothing.
        return self.failed == 0 and self.passed > 0

    def to_dict(self) -> dict:
        return {**asdict(self), "conformant": self.conformant}


def run_conformance(client, ids: list | None = None) -> ConformanceReport:
    target = {
        "gateway_url": client.gateway_url,
        "bus_url": client.bus_url,
        "identity_url": client.identity_url,
        "trust_url": client.trust_url,
        "governance_url": client.governance_url,
        "registry_url": client.registry_url,
    }
    report = ConformanceReport(target=target)
    started = time.monotonic()
    for check in CHECKS:
        if ids and check.id not in ids:
            continue
        result = check.run(client)
        report.results.append({
            "id": check.id, "rfc": check.rfc, "title": check.title,
            "status": result.status, "detail": result.detail,
        })
        if result.status == PASS:
            report.passed += 1
        elif result.status == FAIL:
            report.failed += 1
        elif result.status == SKIP:
            report.skipped += 1
    report.duration_seconds = round(time.monotonic() - started, 2)
    return report
