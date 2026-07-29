import argparse
import json
import sys


def _client(args):
    from aepx import AepxClient

    kwargs = {}
    for attr in ("gateway_url", "bus_url", "identity_url", "trust_url", "governance_url", "registry_url"):
        value = getattr(args, attr.replace("_url", ""), None)
        if value:
            kwargs[attr] = value
    return AepxClient(**kwargs)


def _add_target_args(p):
    # Every protocol-touching subcommand can be pointed at a non-default
    # deployment — the same URLs AepxClient defaults from the Operational
    # Manual port map.
    p.add_argument("--gateway", help="Gateway URL (default http://localhost:8000)")
    p.add_argument("--bus", help="Connector Bus URL (default http://localhost:8020)")
    p.add_argument("--identity", help="Identity URL (default http://localhost:8001)")
    p.add_argument("--trust", help="Trust URL (default http://localhost:8002)")
    p.add_argument("--governance", help="Governance URL (default http://localhost:8009)")
    p.add_argument("--registry", help="Registry URL (default http://localhost:8003)")


def main():
    parser = argparse.ArgumentParser(prog="aepx")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Scaffold a new AEP-X agent project")
    create = sub.add_parser("create", help="Create an agent, workflow, or platform")
    create.add_argument("kind", choices=["agent", "workflow"])
    create.add_argument("name")
    run = sub.add_parser("run", help="Run an agent locally against the Gateway")
    run.add_argument("agent_name")
    run.add_argument("prompt")
    sub.add_parser("deploy", help="Deploy via the Helm chart (see charts/aepx-service)")

    test = sub.add_parser("test", help="Run the RFC-0007 conformance suite against a live deployment")
    test.add_argument("--check", action="append", dest="checks", help="run only this check id (repeatable)")
    test.add_argument("--json", action="store_true", help="emit the raw report as JSON")
    _add_target_args(test)

    did = sub.add_parser("did", help="Decentralized identity (did:key, RFC-0006)")
    did_sub = did.add_subparsers(dest="did_command", required=True)
    _add_target_args(did_sub.add_parser("create", help="Mint a fresh did:key"))
    did_resolve = did_sub.add_parser("resolve", help="Resolve a did:key into its DID Document")
    did_resolve.add_argument("did")
    _add_target_args(did_resolve)

    invoke = sub.add_parser("invoke", help="Invoke a connector through the trust/policy-gated bus")
    invoke.add_argument("connector")
    invoke.add_argument("--payload", default="{}", help="JSON payload (default {})")
    invoke.add_argument("--sender", default="aepx://agent/cli")
    _add_target_args(invoke)

    plugins = sub.add_parser("plugins", help="List attached SDK plugins (built-in + entry-point discovered)")
    _add_target_args(plugins)

    args = parser.parse_args()

    if args.command == "init":
        print("Scaffold: create your service under services/<name>/ following the shared template.")
    elif args.command == "create":
        print(f"Scaffold: would create {args.kind} '{args.name}'.")
    elif args.command == "run":
        from aepx import Agent

        agent = Agent(args.agent_name)
        print(agent.execute(args.prompt))
    elif args.command == "deploy":
        print("Scaffold: run `helm install <name> ./charts/aepx-service -f values-<name>.yaml`.")
    elif args.command == "test":
        return _cmd_test(args)
    elif args.command == "did":
        return _cmd_did(args)
    elif args.command == "invoke":
        return _cmd_invoke(args)
    elif args.command == "plugins":
        return _cmd_plugins(args)
    return 0


def _cmd_test(args):
    from aepx.conformance import run_conformance

    report = run_conformance(_client(args), ids=args.checks)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for r in report.results:
            mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[r["status"]]
            print(f"  [{mark}] {r['id']} ({r['rfc']}) — {r['detail']}")
        print(f"\nconformance: {report.passed} passed, {report.failed} failed, "
              f"{report.skipped} skipped in {report.duration_seconds}s "
              f"-> {'CONFORMANT' if report.conformant else 'NOT CONFORMANT'}")
    return 0 if report.conformant else 1


def _cmd_did(args):
    client = _client(args)
    if args.did_command == "create":
        print(json.dumps(client.did.create(), indent=2))
    else:
        try:
            print(json.dumps(client.did.resolve(args.did), indent=2))
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return 0


def _cmd_invoke(args):
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as e:
        print(f"error: --payload is not valid JSON: {e}", file=sys.stderr)
        return 1
    result = _client(args).connectors.invoke(args.connector, payload, sender=args.sender)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == 200 else 1


def _cmd_plugins(args):
    client = _client(args)
    # Re-discover to also show entry-point plugins beyond the built-ins.
    from aepx.client import _discover_entry_point_plugins

    discovered = {p.name for p in _discover_entry_point_plugins()}
    for name, plugin in sorted(client.plugins.items()):
        source = "builtin+entry-point" if name in discovered else "builtin"
        print(f"  {name:<12} {type(plugin).__module__}.{type(plugin).__name__} ({source})")
    for name in sorted(discovered - set(client.plugins)):
        print(f"  {name:<12} (entry-point, not attached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
