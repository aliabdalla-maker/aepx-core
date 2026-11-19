# Autonomous pilot budget admission (offline only)

`scripts/aepx_budget_admission.py` provides a pure fail-closed validator for planned work against token, USD cost, wall-clock seconds and repair-attempt limits. It requires complete limit/used/planned dictionaries, nonnegative integer counts and finite decimal-string USD amounts. A successful decision **does not reserve funds or authorize external execution**.

Example:

```python
from aepx_budget_admission import admit
print(admit(
 {"tokens":1000,"cost_usd":"2.00","seconds":120,"repair_attempts":3},
 {"tokens":200,"cost_usd":"0.50","seconds":20,"repair_attempts":1},
 {"tokens":300,"cost_usd":"0.75","seconds":30,"repair_attempts":1}))
```

This is a precondition, not a complete budget-enforcement system. A future runner must persist atomic reservations, use trusted provider usage/cost reports, settle or release reservations after failure, prevent concurrent overspend, enforce wall-clock deadlines externally and stop when usage data is unavailable. It must never enable provider calls, deployment, auto-merge or external MCP execution merely because admission succeeds.

## Offline reservation prototype

`scripts/aepx_budget_ledger.py` provides `reserve(path, request_id, limits, planned)` and `settle(path, request_id, actual)`. A stable request ID prevents duplicate reservations; a held reservation counts at its maximum until settled. A settlement cannot exceed its reservation. Ledger writes use a cooperative exclusive directory lock and atomic replacement.

**Important limitations:** This is single-host, trusted-directory, cooperative-writer prototype code, not a database transaction or an authorization mechanism. It has no trusted provider usage source, identity binding, reconciliation service, crash recovery protocol, distributed lock, tamper-evident audit, or reliable cross-host concurrency. Do not use it for actual paid API spend or multi-worker production traffic. Never automatically release in-flight reservations following an unknown crash. Real provider execution remains disabled.

## Ledger integrity bounds

Offline reservation ledgers now reject persisted invalid request identifiers, more than 10,000 reservation entries, and files larger than 4 MiB. The exact pretty-printed JSON payload is checked before replacement to avoid writing an oversized file. These are defensive limits, not protection against malicious same-user processes or a substitute for database-backed concurrency, signatures and trusted billing reconciliation.

## Exact-byte serialization

The offline ledger writer now builds one deterministic JSON payload, checks its UTF-8 byte length against the 4 MiB cap, and writes that exact payload to the atomic temporary file. Reserve and settlement regression tests assert the persisted bytes match the expected serialization. This does not make the ledger tamper-evident or distributed-safe.
