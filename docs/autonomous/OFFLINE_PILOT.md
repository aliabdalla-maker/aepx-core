# AEP-X offline pilot executor

This is a **bounded, opt-in local test runner**, not a 10,000-iteration coding agent. It makes no OpenAI API calls and does not edit source, commit, merge or deploy.

Only run against a trusted checkout in a **disposable sandbox**. Even allowlisted Python tests execute repository code; a timeout and reduced environment do not provide OS-level isolation.

Dry run:
```bash
python scripts/aepx_autonomous_pilot.py --pattern test_aepx_autonomous_checkpoint.py
```

Explicit local execution inside a disposable sandbox:
```bash
python scripts/aepx_autonomous_pilot.py --pattern test_aepx_autonomous_checkpoint.py --execute --timeout 60
```

Next: validate CI, add genuine OS/container sandboxing with disabled egress, implement API usage metering from trusted responses and cost estimation, create resumable orchestration, and perform a supervised pilot. Do not enable external MCP execution, auto-merge or production deployment.

## Optional persistent pilot checkpoint

Inside a disposable, network-restricted sandbox, run one explicitly approved test attempt:

```bash
python scripts/aepx_autonomous_pilot.py --pattern test_aepx_autonomous_checkpoint.py --execute --timeout 60 --checkpoint pilot-checkpoint.json
```

The checkpoint records **test attempts**, not autonomous code-development iterations. It is written atomically and can be read on a subsequent run. An exclusive checkpoint lock prevents concurrent writers from silently losing attempts. If a process crashes, the lock may remain: verify no writer is running before manually removing the `.lock` directory. The system deliberately never auto-breaks a lock. Unexpected power loss and cross-filesystem durability remain outside the current acceptance evidence. Keep checkpoint files out of source control if they contain operational metadata. The checkpoint does not contain raw test output or secrets. Never treat a passing pilot test as production release approval.

Regression test:

```bash
python -m unittest discover -s tests -p 'test_aepx_pilot_checkpoint.py' -v
```

Remaining requirements: OS-level isolation, authenticated LLM orchestration, measured API spend and token budgets, concurrency-safe checkpoint locking, supervised 100-attempt pilot, CI acceptance and a release gate.

## Bounded supervised batch (opt-in)

A separate offline batch controller can repeat an allowlisted test **up to 100 times per invocation**, with a 1–3600-second wall-clock limit, a 1–120-second per-test timeout, persistent checkpoint recording and immediate stop on failure. This is **not** an LLM-driven code repair loop, and does not make 100 tests equivalent to 100 autonomous development iterations.

Dry-run:

```bash
python scripts/aepx_supervised_batch.py --pattern test_aepx_autonomous_checkpoint.py --checkpoint /tmp/aepx-pilot.json --count 10
```

Run only in an approved disposable OS-isolated sandbox:

```bash
python scripts/aepx_supervised_batch.py --pattern test_aepx_autonomous_checkpoint.py --checkpoint /tmp/aepx-pilot.json --count 10 --max-seconds 600 --execute
```

The checkpoint must be an absolute path. Never execute repository tests on production infrastructure. This pilot does not provide OS isolation itself. Do not enable LLM actions, auto-merge, external MCP forwarding, or deployment based on this batch report.
