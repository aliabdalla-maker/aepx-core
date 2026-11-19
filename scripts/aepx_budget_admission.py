"""Offline, fail-closed admission for planned agentic work.

This module does not call providers, charge accounts, or authorize execution.
"""
from decimal import Decimal, InvalidOperation

class BudgetDenied(ValueError):
    pass

def _integer(value, name):
    if type(value) is not int or value < 0:
        raise BudgetDenied(f"{name} must be a nonnegative integer")
    return value

def _money(value, name):
    if not isinstance(value, str):
        raise BudgetDenied(f"{name} must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise BudgetDenied(f"invalid {name}") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -6:
        raise BudgetDenied(f"invalid {name}")
    return amount

def admit(limits, used, planned):
    """Return a read-only admission decision; no reservation is persisted.

    Reject missing keys, unknown limits, negative/float values and overflow.
    A caller MUST atomically reserve admitted budgets before making an API call.
    """
    if any(not isinstance(x, dict) for x in (limits, used, planned)):
        raise BudgetDenied("budgets must be objects")
    keys = ("tokens", "cost_usd", "seconds", "repair_attempts")
    if any(set(x) != set(keys) for x in (limits, used, planned)):
        raise BudgetDenied("budget fields missing or unexpected")
    for key in keys:
        if key == "cost_usd":
            cap, consumed, requested = (_money(x[key], key) for x in (limits, used, planned))
        else:
            cap, consumed, requested = (_integer(x[key], key) for x in (limits, used, planned))
        if consumed > cap or requested > cap - consumed:
            raise BudgetDenied(f"{key} budget exhausted")
    return {"admitted": True, "reserved": False, "external_execution_authorized": False}
