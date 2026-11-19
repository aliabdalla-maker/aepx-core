"""Isolated agent dispatcher: runs approved agent jobs one at a time, forever.

Start only inside the worker container of the production compose, which sits on an
internal-only Docker network whose sole routes are the IDE database and the egress gateway.
Before doing anything it proves that boundary from the inside: a direct connection to the
public internet must fail and the gateway must answer. Only then does it attest network
isolation for this process (IDE_NETWORK_ISOLATION_ATTESTED) and start claiming work.
"""
import logging
import os
import socket
import sys
import time

log = logging.getLogger("aepx.agent-dispatcher")

PROBES = (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 53))


def direct_egress_blocked(probes=PROBES, connect=socket.create_connection) -> bool:
    for host, port in probes:
        try:
            conn = connect((host, port), timeout=3)
        except OSError:
            continue
        conn.close()
        return False
    return True


def gateway_reachable(connect=socket.create_connection) -> bool:
    try:
        connect(("gateway", 8080), timeout=3).close()
        return True
    except OSError:
        return False


def attest_isolation(connect=socket.create_connection) -> None:
    if not direct_egress_blocked(connect=connect):
        raise SystemExit("Refusing to start: this container can reach the internet directly")
    if not gateway_reachable(connect=connect):
        raise SystemExit("Refusing to start: egress gateway unreachable")
    os.environ["IDE_NETWORK_ISOLATION_ATTESTED"] = "true"


def run_forever(idle_seconds: float = 3.0, max_loops: int | None = None) -> None:
    from sqlalchemy import text
    from .main import SessionLocal
    from .metered_worker import execute_next_metered
    loops = 0
    while max_loops is None or loops < max_loops:
        loops += 1
        try:
            with SessionLocal() as db:
                tenants = [r[0] for r in db.execute(
                    text("SELECT tenant_id FROM ide_dispatchable_tenants(20)")).all()]
                db.rollback()
        except Exception as exc:  # database restarting: back off and retry
            log.warning("queue unavailable: %s", type(exc).__name__)
            time.sleep(10)
            continue
        worked = False
        for tenant in tenants:
            try:
                outcome = execute_next_metered(tenant)
            except Exception as exc:
                log.error("dispatch error: %s", type(exc).__name__)
                continue
            worked = worked or outcome != "empty"
            log.info("run outcome=%s", outcome)
        if not worked:
            time.sleep(idle_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    for name in ("IDE_EXTERNAL_EXECUTION_ENABLED", "IDE_GOVERNED_WORKER_ENABLED",
                 "IDE_EGRESS_GATEWAY_VERIFIED", "IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED"):
        if os.getenv(name) != "true":
            log.info("agents disabled (%s is not true); idling", name)
            while True:
                time.sleep(3600)
    attest_isolation()
    log.info("network isolation verified; dispatching approved agent runs")
    run_forever()


if __name__ == "__main__":
    main()
