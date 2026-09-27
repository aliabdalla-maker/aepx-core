---
name: aepx-cli
description: The aepx CLI (cli/aepx_cli/__main__.py) — every subcommand (init, create, run, deploy, test, did create/resolve, invoke, plugins), its exact argparse flags, exit codes and examples. Use when running or changing the aepx command, or scripting conformance and connector calls.
---

# AEP-X CLI (`cli/aepx_cli`)

A single argparse file, `cli/aepx_cli/__main__.py`, with `prog="aepx"`. There is no `pyproject.toml` or console-script entry point for the CLI, so no `aepx` executable gets installed. Run it with Python, with the SDK importable:

```bash
pip install -e sdk/python                    # the CLI imports `aepx`
python cli/aepx_cli/__main__.py --help       # run as a script from the repo root
# or: cd cli && python -m aepx_cli --help
```

The examples below write `aepx` as shorthand for one of those invocations.

## Target flags (shared)

`test`, `did create`, `did resolve`, `invoke` and `plugins` all accept these flags, which map onto `AepxClient` URLs. Unset flags fall back to the SDK defaults:

| Flag | Default |
|---|---|
| `--gateway` | http://localhost:8000 |
| `--bus` | http://localhost:8020 |
| `--identity` | http://localhost:8001 |
| `--trust` | http://localhost:8002 |
| `--governance` | http://localhost:8009 |
| `--registry` | http://localhost:8003 |

There is no flag for the oracle-bridge URL. The CLI has no oracle or chain subcommands; use the SDK for those.

## Subcommands

| Command | Arguments / flags | Behaviour |
|---|---|---|
| `init` | none | Scaffold only: prints a pointer to `services/<name>/`. |
| `create` | `kind` (`agent` or `workflow`), `name` | Scaffold only: prints `would create ...`. |
| `run` | `agent_name`, `prompt` | `Agent(agent_name).execute(prompt)` against the Gateway at localhost:8000. Takes no target flags. |
| `deploy` | none | Scaffold only: prints a `helm install ... ./charts/aepx-service` hint. There is no `charts/` directory in the repo. |
| `test` | `--check ID` (repeatable, stored as `checks`), `--json`, target flags | Runs the RFC-0007 conformance suite. |
| `did create` | target flags | Mints a did:key and prints JSON. |
| `did resolve` | `did`, target flags | Prints the DID Document. A malformed DID prints `error: ...` to stderr and exits 1. |
| `invoke` | `connector`, `--payload JSON` (default `{}`), `--sender` (default `aepx://agent/cli`), target flags | Governed connector call through the bus. |
| `plugins` | target flags | Lists attached SDK plugins and their source. |

## Exit codes

- `test`: 0 if the deployment is conformant (no FAIL results and at least one PASS), otherwise 1. You can use this directly as a CI gate.
- `invoke`: 0 if the bus returned status 200. Otherwise 1, including trust or policy denials (403) and an open circuit (503). An invalid `--payload` JSON prints an error and exits 1.
- `did resolve`: 1 on a malformed DID.
- Everything else: 0.

## Examples

```bash
# conformance against the local stack, human-readable
aepx test
#   [PASS] core.envelope-shape (RFC-0001) — ...
#   conformance: N passed, N failed, N skipped in Xs -> CONFORMANT | NOT CONFORMANT

# only two checks, raw JSON report, against another deployment
aepx test --check did.roundtrip --check ledger.verify --json --gateway http://gw:8000 --bus http://bus:8000

# identity
aepx did create
aepx did resolve did:key:z6Mk...

# governed connector calls
aepx invoke salesforce --payload '{"op":"lookup_contact"}'      # min_trust 50, AIA-R1
aepx invoke ethereum --payload '{"method":"eth_blockNumber","params":[]}' --sender aepx://agent/<id>
#   ethereum needs trust >= 60; a fresh sender starts at 50 and gets a 403 trust denial
aepx invoke opcua        # industrial: min_trust 70 and AIA-R3 -> 403 -> exit 1

# talk to the Gateway as an agent
aepx run tutor "Explain Newton's Laws"

aepx plugins
```

## `plugins` output

For each attached plugin, `plugins` prints `name  module.Class (builtin)`. When the SDK is pip-installed, the built-ins are also published as entry points, so they show as `(builtin+entry-point)`. The command builds its client without `discover_plugins=True`, so any third-party entry-point plugins are listed as `(entry-point, not attached)`.

## Changing the CLI

- Add a subparser in `main()`. If it talks to the protocol, call `_add_target_args(p)` on it, then dispatch to a `_cmd_<name>(args)` function that returns an exit code.
- `_client(args)` builds the `AepxClient` from the flags. Its keys are derived as `attr.replace("_url", "")`, so a new target flag must be named `--<x>` to match an `<x>_url` client kwarg.
- The CLI has no dedicated tests or CI matrix entry. Test the SDK behaviour you call in `sdk/python/tests`, and run `ruff check cli` by hand.

## Related skills

- `aepx-sdk` — the client and plugins the CLI wraps
- `aepx-rfcs-conformance` — what `aepx test` checks
- `aepx-connector-bus` — why `invoke` can return 403 or 503
- `aepx-run-stack` — bring up the stack the CLI targets
