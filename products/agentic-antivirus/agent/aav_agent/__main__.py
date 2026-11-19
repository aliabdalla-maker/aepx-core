"""CLI: python -m aav_agent enrol|run|scan|status --state DIR"""
from __future__ import annotations

import argparse
import json
import os
import sys

from aav_agent.agent import Agent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aav-agent")
    ap.add_argument("--state", default=os.getenv("AAV_AGENT_STATE",
                                                 "C:\\ProgramData\\AgenticAntivirus" if os.name == "nt"
                                                 else "/var/lib/aav-agent"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enrol")
    e.add_argument("--url", required=True)
    e.add_argument("--token", required=True)
    sub.add_parser("run").add_argument("--interval", type=float, default=10.0)
    s = sub.add_parser("scan")
    s.add_argument("paths", nargs="*")
    s.add_argument("--type", default="quick", choices=["quick", "full"])
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "enrol":
        ag = Agent(a.state, base_url=a.url)
        ident = ag.enrol(a.token)
        print(json.dumps({"device_id": ident["device_id"], "tenant_id": ident["tenant_id"]}))
        return 0
    ag = Agent(a.state)
    if a.cmd == "run":
        ag.run_forever(a.interval)
    elif a.cmd == "scan":
        ag.refresh_updates()
        print(json.dumps(ag.scan_paths(a.paths or ag.default_scan_paths(a.type), trigger=f"{a.type}_scan")))
        ag.flush()
    elif a.cmd == "status":
        print(json.dumps({"device_id": ag.identity["device_id"], "definitions": ag.state.get("active:detections"),
                          "policy_version": (ag.state.get("policy") or {}).get("bundle", {}).get("version"),
                          "buffered_bytes": ag.state.buffered_bytes(), "quarantine": len(ag.vault.items())}))
    return 0


def run() -> int:
    try:
        return main()
    except RuntimeError as exc:
        print(f"aav-agent: {exc}. Run 'aav-agent enrol --url URL --token TOKEN' first.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(run())
