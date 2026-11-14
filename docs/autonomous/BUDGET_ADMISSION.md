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
