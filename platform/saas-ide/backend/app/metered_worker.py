"""Metered governed worker: one approved agent job, billed against the provider's own receipt.

Same fail-closed gates and fenced lease protocol as governed_worker.execute_next, plus:
  * a platform-wide monthly AI spend cap (IDE_AI_MONTHLY_CAP_MICROUSD), reserved atomically
    before every provider call, so total spend can never exceed the owner's cap;
  * a per-plan daily allowance (free / trial / pro), checked against the tenant's own usage;
  * provider usage reconciliation: OpenRouter returns tokens and USD cost per call, and that
    figure is what is charged. When the provider does not report a cost (timeout, crash,
    malformed reply) the full reservation is charged instead, which can only under-spend.
Never call this without the isolated network the gateway deployment provides.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from .main import SessionLocal
from .phase23 import (fenced_claim, record_fenced_result, reserve_budget, settle_budget,
                      settle_reserved_maximum)
from .providers import generate_metered
from .subscriptions import ensure_entitlement, entitlement_state
from .timeout23 import hard_deadline

# Daily AI allowance per plan, in micro-USD. Overridable per deployment.
DEFAULT_DAILY_ALLOWANCE = {"free": 50_000, "trial": 200_000, "pro": 1_000_000}

SYSTEM_PROMPT = (
    "You are the AEP-X IDE agent crew: requirements analyst, architect, developer, "
    "media producer and verifier working together. Answer the user's task directly with "
    "concrete, production-quality output: code in fenced blocks with file names, "
    "step-by-step plans, scripts, storyboards, shot lists, music briefs or social posts as "
    "the task needs. Nothing you propose is executed or published until the user approves "
    "it in the IDE, so say what should be reviewed. Follow this plan:\n"
)


def _env_int(name: str, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, "0"))
    except ValueError:
        value = 0
    if not low <= value <= high:
        raise ValueError(f"{name} must be explicitly configured")
    return value


def daily_allowance(plan: str) -> int:
    value = os.getenv("IDE_AI_DAILY_MICROUSD_" + plan.upper(), "")
    if value.isdigit():
        return int(value)
    return DEFAULT_DAILY_ALLOWANCE.get(plan, DEFAULT_DAILY_ALLOWANCE["free"])


def month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def reserve_monthly(db, month: str, micro_usd: int, cap: int) -> bool:
    """Atomically reserve against the platform monthly cap; False when it would be exceeded."""
    db.execute(text("""INSERT INTO ide_ai_monthly_spend(month) VALUES (:m)
                       ON CONFLICT (month) DO NOTHING"""), {"m": month})
    row = db.execute(text("""UPDATE ide_ai_monthly_spend
        SET reserved_microusd = reserved_microusd + :c, runs = runs + 1
        WHERE month = :m AND spent_microusd + reserved_microusd + :c <= :cap
        RETURNING month"""), {"m": month, "c": micro_usd, "cap": cap}).first()
    if row is None:
        db.rollback()
        return False
    db.commit()
    return True


def settle_monthly(db, month: str, reserved: int, actual: int) -> None:
    db.execute(text("""UPDATE ide_ai_monthly_spend
        SET reserved_microusd = GREATEST(reserved_microusd - :r, 0),
            spent_microusd = spent_microusd + :a
        WHERE month = :m"""), {"m": month, "r": reserved, "a": actual})
    db.commit()


def _scope(db, tenant: str) -> None:
    db.execute(text("SELECT set_config('ide.tenant_id', :t, true)"), {"t": tenant})


def spent_today(db, tenant: str, subject: str) -> int:
    _scope(db, tenant)
    value = db.execute(text("""SELECT COALESCE(SUM(COALESCE(actual_microusd, reserved_microusd)),0)
        FROM ide_ai_usage WHERE tenant_id=:t AND subject=:s
          AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"""),
        {"t": tenant, "s": subject}).scalar()
    db.rollback()
    return int(value or 0)


def _authorized(db, tenant: str, job_id: str, owner: str, fence: int):
    """Fresh check against the database immediately before the provider call."""
    _scope(db, tenant)
    row = db.execute(text("""SELECT r.id, r.subject, r.model_route, r.request, r.plan
        FROM ide_agent_runs r JOIN ide_agent_jobs j ON j.run_id=r.id AND j.tenant_id=r.tenant_id
        WHERE r.tenant_id=:t AND j.id=:j AND j.fencing_token=:f AND j.lease_owner=:o
          AND j.state='leased' AND j.lease_until>now() AND r.status IN ('approved','running')"""),
        {"t": tenant, "j": job_id, "f": fence, "o": owner}).first()
    db.rollback()
    return row


def build_prompt(plan_json: str, request: str) -> tuple[str, str]:
    try:
        steps = json.loads(plan_json or "[]")
    except ValueError:
        steps = []
    plan = "\n".join(f"- {s.get('agent')}: {s.get('goal')}" for s in steps
                     if isinstance(s, dict))[:3500]
    return (SYSTEM_PROMPT + plan)[:4000], request[:16000]


def _receipt_value(receipt, key):
    return receipt.get(key) if isinstance(receipt, dict) else None


def execute_next_metered(tenant_id: str, *, owner: str | None = None, call=generate_metered) -> str:
    if (os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED") != "true"
            or os.getenv("IDE_GOVERNED_WORKER_ENABLED") != "true"):
        raise PermissionError("Governed worker disabled")
    if os.getenv("IDE_EGRESS_GATEWAY_VERIFIED") != "true":
        raise PermissionError("Reviewed network egress gateway required")
    if os.getenv("IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED") != "true":
        raise PermissionError("Provider spend reconciliation required")
    if not tenant_id or len(tenant_id) > 128:
        raise ValueError("Invalid tenant")
    tokens = _env_int("IDE_WORKER_MAX_TOKENS", 1, 2000)
    reserve = _env_int("IDE_WORKER_MAX_MICROUSD", 1, 5_000_000)
    seconds = _env_int("IDE_WORKER_TIMEOUT_SECONDS", 1, 60)
    cap = _env_int("IDE_AI_MONTHLY_CAP_MICROUSD", 1, 1_000_000_000)
    owner = owner or str(uuid.uuid4())

    with SessionLocal() as db:
        db.execute(text("SELECT ide_ensure_agent_budget(:t, :c)"), {"t": tenant_id, "c": cap})
        db.commit()
    with SessionLocal() as db:
        claim = fenced_claim(db, tenant_id, owner, lease_seconds=60)
    if claim is None:
        return "empty"
    job_id, fence = str(claim["job_id"]), claim["fencing_token"]

    def finish(output: str, success: bool) -> bool:
        with SessionLocal() as db:
            return record_fenced_result(db, tenant_id, job_id, owner, fence, output, success)

    with SessionLocal() as db:
        row = _authorized(db, tenant_id, job_id, owner, fence)
    if row is None or row.model_route == "unconfigured":
        finish("No AI model is configured for this workspace yet.", False)
        return "unconfigured"

    with SessionLocal() as db:
        ent = ensure_entitlement(db, row.subject)
    plan = entitlement_state(ent["trial_started_at"], ent["status"], ent["current_period_end"])["plan"]
    with SessionLocal() as db:
        used = spent_today(db, tenant_id, row.subject)
    if used + reserve > daily_allowance(plan):
        finish(f"Today's AI allowance for the {plan} plan is used up. It resets at midnight UTC"
               + ("" if plan == "pro" else "; subscribe for a larger daily allowance") + ".", False)
        return "allowance_exhausted"

    month = month_key()
    with SessionLocal() as db:
        if not reserve_monthly(db, month, reserve, cap):
            finish("The platform's monthly AI budget has been reached. Agents resume next month.", False)
            return "monthly_cap_reached"
    usage_id = str(uuid.uuid4())
    with SessionLocal() as db:
        _scope(db, tenant_id)
        db.execute(text("""INSERT INTO ide_ai_usage(id,tenant_id,subject,run_id,month,provider,reserved_microusd)
            VALUES (:id,:t,:s,:r,:m,:p,:c)"""), {"id": usage_id, "t": tenant_id, "s": row.subject,
            "r": row.id, "m": month, "p": row.model_route, "c": reserve})
        db.commit()

    reservation = None
    receipt = None
    try:
        with SessionLocal() as db:
            reservation = reserve_budget(db, tenant_id, job_id, fence, tokens, reserve)
        with SessionLocal() as db:
            current = _authorized(db, tenant_id, job_id, owner, fence)
        if current is None:
            raise PermissionError("Run cancelled or lease lost before dispatch")
        system, prompt = build_prompt(current.plan, current.request)
        receipt = hard_deadline(call, current.model_route, prompt, max_tokens=tokens,
                                seconds=seconds, system=system)
        if not isinstance(receipt, dict) or not isinstance(receipt.get("text"), str):
            raise ValueError("Provider output must be text")
        output, success = receipt["text"] or "(The model returned an empty answer.)", True
    except Exception:
        output, success = "The agent could not finish this run (provider error or timeout). Try again.", False
    finally:
        cost = _receipt_value(receipt, "cost_microusd")
        metered = isinstance(cost, int) and not isinstance(cost, bool) and 0 <= cost <= reserve
        charged = cost if metered else reserve
        if reservation is not None:
            with SessionLocal() as db:
                try:
                    if metered:
                        used_tokens = min(int(_receipt_value(receipt, "completion_tokens") or 0), tokens)
                        settle_budget(db, tenant_id, reservation, used_tokens, cost)
                    else:
                        settle_reserved_maximum(db, tenant_id, reservation)
                except (ValueError, PermissionError):
                    db.rollback()
        with SessionLocal() as db:
            settle_monthly(db, month, reserve, charged)
        with SessionLocal() as db:
            _scope(db, tenant_id)
            db.execute(text("""UPDATE ide_ai_usage SET actual_microusd=:a, state=:st, model=:mo,
                provider_request_id=:rq, prompt_tokens=:pt, completion_tokens=:ct
                WHERE tenant_id=:t AND id=:id"""), {
                "a": charged, "st": "settled" if metered else "charged_max",
                "mo": str(_receipt_value(receipt, "model") or "")[:120],
                "rq": _receipt_value(receipt, "request_id"),
                "pt": _receipt_value(receipt, "prompt_tokens"),
                "ct": _receipt_value(receipt, "completion_tokens"),
                "t": tenant_id, "id": usage_id})
            db.commit()
    committed = finish(output, success)
    return ("completed" if success else "failed") if committed else "stale_or_cancelled"
