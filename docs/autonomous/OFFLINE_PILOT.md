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
