#!/usr/bin/env python3
"""Endpoint scale test (NFR-02, B-09): simulates N agents against a control plane and reports latency percentiles,
error rates and throughput, then a reconnect storm (every agent reconnects at once with a buffered backlog).

  python tools/load_test.py --api https://staging-host/api --token ENROLMENT_TOKEN --agents 1000 \
      --minutes 10 --evidence load-1000.json

Each simulated agent enrols once (the token needs max_uses >= agents), then every --interval seconds sends a
heartbeat and a batch of --events telemetry events, like the real agent. Run it against STAGING (or a dedicated
environment), never production: it creates N devices in the token's tenant. Pass criteria (D-06 defaults, override
with flags): p95 heartbeat < 1000 ms, p95 event batch < 2000 ms, error rate < 1 %.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
import uuid
from datetime import datetime, timezone

import httpx


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p / 100 * len(xs)))], 1)


class Stats:
    def __init__(self):
        self.lat: dict[str, list[float]] = {}
        self.err: dict[str, int] = {}
        self.ok: dict[str, int] = {}

    def add(self, op: str, ms: float, ok: bool):
        (self.lat.setdefault(op, []).append(ms) if ok else None)
        d = self.ok if ok else self.err
        d[op] = d.get(op, 0) + 1

    def report(self) -> dict:
        out = {}
        for op in sorted(set(self.ok) | set(self.err)):
            n_ok, n_err = self.ok.get(op, 0), self.err.get(op, 0)
            xs = self.lat.get(op, [])
            out[op] = {"requests": n_ok + n_err, "errors": n_err,
                       "error_rate": round(n_err / max(1, n_ok + n_err), 4),
                       "p50_ms": pct(xs, 50), "p95_ms": pct(xs, 95), "p99_ms": pct(xs, 99),
                       "mean_ms": round(statistics.mean(xs), 1) if xs else None}
        return out


async def timed(stats: Stats, op: str, coro):
    t0 = time.perf_counter()
    try:
        r = await coro
        ok = r.status_code < 400
        stats.add(op, (time.perf_counter() - t0) * 1000, ok)
        return r if ok else None
    except httpx.HTTPError:
        stats.add(op, (time.perf_counter() - t0) * 1000, False)
        return None


def events(n: int) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    kinds = [("process_start", {"pid": 4242, "process": "notepad.exe", "parent": "explorer.exe", "cmdline": "notepad"}),
             ("network_connection", {"pid": 4242, "remote_ip": "203.0.113.10", "remote_port": 443}),
             ("file_modify", {"path": "C:\\Users\\a\\Documents\\report.docx", "pid": 4242})]
    return [{"event_uid": uuid.uuid4().hex, "kind": k, "occurred_at": now, "data": d}
            for k, d in (random.choice(kinds) for _ in range(n))]


async def agent(i: int, c: httpx.AsyncClient, token: str, stats: Stats, stop: float, interval: float, n_events: int,
                keys: list):
    r = await timed(stats, "enrol", c.post("/v1/agent/enrol", json={
        "token": token, "hostname": f"load-{i:05d}", "os": "windows", "os_version": "11", "agent_version": "0.1.2"}))
    if r is None:
        return
    h = {"X-Device-Key": r.json()["device_key"]}
    keys.append(h)
    await asyncio.sleep(random.uniform(0, interval))                 # spread the fleet like real check-ins
    while time.monotonic() < stop:
        await timed(stats, "heartbeat", c.post("/v1/agent/heartbeat", headers=h, json={
            "agent_version": "0.1.2", "protection_status": "protected", "sensor_health": {"engine": True}}))
        if n_events:
            await timed(stats, "events", c.post("/v1/agent/events", headers=h, json={"events": events(n_events)}))
        await asyncio.sleep(interval)


async def storm(c: httpx.AsyncClient, keys: list, stats: Stats, backlog: int):
    await asyncio.gather(*(timed(stats, "reconnect_events", c.post("/v1/agent/events", headers=h,
                                                                    json={"events": events(backlog)}))
                           for h in keys))


async def main_async(a) -> dict:
    stats = Stats()
    limits = httpx.Limits(max_connections=a.connections, max_keepalive_connections=a.connections)
    async with httpx.AsyncClient(base_url=a.api.rstrip("/"), timeout=30, limits=limits) as c:
        t0 = time.monotonic()
        stop = t0 + a.minutes * 60
        keys: list = []
        await asyncio.gather(*(agent(i, c, a.token, stats, stop, a.interval, a.events, keys) for i in range(a.agents)))
        steady_s = time.monotonic() - t0
        await storm(c, keys, stats, a.backlog)
    rep = stats.report()
    hb, ev = rep.get("heartbeat", {}), rep.get("events", {})
    total = sum(v["requests"] for v in rep.values())
    errors = sum(v["errors"] for v in rep.values())
    checks = {"heartbeat_p95_ms": (hb.get("p95_ms") or 1e9) < a.max_heartbeat_p95,
              "events_p95_ms": (ev.get("p95_ms") or 0) < a.max_events_p95,
              "error_rate": errors / max(1, total) < a.max_error_rate,
              "enrolled_all": len(keys) == a.agents}
    return {"tool": "tools/load_test.py", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "api": a.api, "agents": a.agents, "enrolled": len(keys), "duration_s": round(steady_s, 1),
            "interval_s": a.interval, "events_per_batch": a.events, "reconnect_backlog": a.backlog,
            "throughput_rps": round(total / max(1, steady_s), 1), "operations": rep,
            "criteria": {"heartbeat_p95_ms": a.max_heartbeat_p95, "events_p95_ms": a.max_events_p95,
                         "error_rate": a.max_error_rate},
            "checks": checks, "passed": all(checks.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--agents", type=int, default=1000)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--interval", type=float, default=30)
    ap.add_argument("--events", type=int, default=20)
    ap.add_argument("--backlog", type=int, default=200)
    ap.add_argument("--connections", type=int, default=200)
    ap.add_argument("--max-heartbeat-p95", type=float, default=1000)
    ap.add_argument("--max-events-p95", type=float, default=2000)
    ap.add_argument("--max-error-rate", type=float, default=0.01)
    ap.add_argument("--evidence")
    a = ap.parse_args()
    res = asyncio.run(main_async(a))
    print(json.dumps(res, indent=1))
    if a.evidence:
        with open(a.evidence, "w") as f:
            json.dump(res, f, indent=1)
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
