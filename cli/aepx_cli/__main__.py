import argparse
import sys


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


if __name__ == "__main__":
    sys.exit(main())
