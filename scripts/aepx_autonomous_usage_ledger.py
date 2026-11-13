"""Fail-closed offline API usage accounting for an AEP-X runner.

Only accepts caller-provided trusted provider usage; never estimates from prompts.
The executor must independently authenticate responses and persist this ledger.
"""
from decimal import Decimal, InvalidOperation
import json

class AccountingDenied(ValueError):
    pass

def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise AccountingDenied("amount must be a decimal string or integer")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise AccountingDenied("invalid decimal amount") from exc
    if not result.is_finite() or result < 0:
        raise AccountingDenied("nonfinite or negative amount")
    return result

def validate_ledger(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise AccountingDenied("unsupported ledger")
    cap = money(data.get("cap_usd"))
    total = money(data.get("spent_usd"))
    if cap <= 0 or total > cap:
        raise AccountingDenied("invalid or exceeded budget")
    receipts = data.get("receipts")
    if not isinstance(receipts, dict) or len(receipts) > 10000:
        raise AccountingDenied("invalid receipt collection")
    if any(not isinstance(k,str) or not k or len(k)>256 for k in receipts):
        raise AccountingDenied("invalid receipt identifier")
    computed = sum((money(v["cost_usd"]) for v in receipts.values()
                    if isinstance(v,dict) and "cost_usd" in v),Decimal("0"))
    if len(receipts) != sum(isinstance(v,dict) and "cost_usd" in v for v in receipts.values()):
        raise AccountingDenied("malformed receipt")
    if computed != total:
        raise AccountingDenied("ledger total does not match receipts")
    return data

def record_receipt(ledger, *, request_id, input_tokens, output_tokens,
                   input_usd_per_million, output_usd_per_million):
    validate_ledger(ledger)
    if not isinstance(request_id,str) or not 1 <= len(request_id) <= 256:
        raise AccountingDenied("invalid request id")
    if request_id in ledger["receipts"]:
        raise AccountingDenied("duplicate request id")
    if (type(input_tokens) is not int or type(output_tokens) is not int
            or input_tokens < 0 or output_tokens < 0):
        raise AccountingDenied("token counts must be nonnegative integers")
    if input_tokens + output_tokens == 0:
        raise AccountingDenied("zero-token receipt cannot prove API usage")
    price_in, price_out = money(input_usd_per_million), money(output_usd_per_million)
    if price_in == 0 or price_out == 0:
        raise AccountingDenied("explicit nonzero prices required")
    charge = (Decimal(input_tokens)*price_in +
              Decimal(output_tokens)*price_out)/Decimal(1000000)
    total = money(ledger["spent_usd"]) + charge
    if total >= money(ledger["cap_usd"]):
        raise AccountingDenied("budget reached; stop before further requests")
    result = json.loads(json.dumps(ledger))
    result["spent_usd"] = str(total)
    result["receipts"][request_id] = {"input_tokens":input_tokens,
                                      "output_tokens":output_tokens,
                                      "cost_usd":str(charge)}
    return validate_ledger(result)

def can_start_request(ledger, *, reserved_usd):
    validate_ledger(ledger)
    reserve = money(reserved_usd)
    if reserve <= 0 or money(ledger["spent_usd"]) + reserve >= money(ledger["cap_usd"]):
        raise AccountingDenied("insufficient budget for reserved request")
    return True
