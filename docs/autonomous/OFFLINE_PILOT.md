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

The checkpoint records **test attempts**, not autonomous code-development iterations. It is written atomically and can be read on a subsequent run. Use **one writer only**; concurrent processes and unexpected power loss are not fully covered by this implementation. Keep checkpoint files out of source control if they contain operational metadata. The checkpoint does not contain raw test output or secrets. Never treat a passing pilot test as production release approval.

Regression test:

```bash
python -m unittest discover -s tests -p 'test_aepx_pilot_checkpoint.py' -v
```

Remaining requirements: OS-level isolation, authenticated LLM orchestration, measured API spend and token budgets, concurrency-safe checkpoint locking, supervised 100-attempt pilot, CI acceptance and a release gate.
