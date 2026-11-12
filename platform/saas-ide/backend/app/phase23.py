"""Phase 2.3 fenced job operations and transactionally reserved tenant budgets."""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

def _scope(db: Session, tenant: str):
    # SET LOCAL expires at commit; each public operation establishes a new scope.
    # Tenant identity must be authorized by the caller, never by this helper.
    if not tenant or len(tenant)>128:
        raise ValueError("Invalid tenant")
    db.execute(text("SELECT set_config('ide.tenant_id', :tenant, true)"), {"tenant":tenant})

def fenced_claim(db: Session, tenant: str, owner: str, lease_seconds: int = 45):
    if not tenant or not owner or len(owner)>100 or not 5<=lease_seconds<=60:
        raise ValueError("Invalid worker identity or lease")
    _scope(db, tenant)
    row=db.execute(text("""
      SELECT j.id,j.run_id,j.fencing_token FROM ide_agent_jobs j
      JOIN ide_agent_runs r ON r.id=j.run_id AND r.tenant_id=j.tenant_id
      WHERE j.tenant_id=:tenant AND j.attempt<2
        AND j.next_attempt_at<=now()
        AND (j.state='pending' OR (j.state='leased' AND j.lease_until<now()))
        AND r.status IN ('approved','running')
      ORDER BY j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1
    """),{"tenant":tenant}).mappings().first()
    if row is None:
        db.rollback()
        return None
    token=row["fencing_token"]+1
    db.execute(text("""UPDATE ide_agent_jobs SET state='leased',attempt=attempt+1,
       lease_owner=:owner,lease_until=now()+(:seconds * interval '1 second'),
       fencing_token=:token WHERE id=:id AND tenant_id=:tenant"""),
       {"owner":owner,"seconds":lease_seconds,"token":token,"id":row["id"],"tenant":tenant})
    db.commit()
    return {"job_id":row["id"],"run_id":row["run_id"],"fencing_token":token}

def heartbeat(db: Session, tenant: str, job_id: str, owner: str, token: int, seconds: int = 45) -> bool:
    if not 5<=seconds<=60:
        raise ValueError("Invalid lease duration")
    _scope(db, tenant)
    result=db.execute(text("""UPDATE ide_agent_jobs
       SET lease_until=now()+(:seconds * interval '1 second')
       WHERE tenant_id=:tenant AND id=:job AND lease_owner=:owner AND fencing_token=:token
       AND state='leased' AND lease_until>now() RETURNING id"""),
       {"seconds":seconds,"tenant":tenant,"job":job_id,"owner":owner,"token":token}).first()
    db.commit()
    return result is not None

def fenced_finish(db: Session, tenant: str, job_id: str, owner: str, token: int, success: bool) -> bool:
    # A stale worker can never commit results after lease expiry or replacement.
    _scope(db, tenant)
    row=db.execute(text("""UPDATE ide_agent_jobs SET state=:state,completed_at=now(),
       lease_owner=NULL,lease_until=NULL
       WHERE tenant_id=:tenant AND id=:job AND lease_owner=:owner
       AND fencing_token=:token AND state='leased' AND lease_until>now()
       RETURNING run_id"""),{"state":"completed" if success else "failed",
         "tenant":tenant,"job":job_id,"owner":owner,"token":token}).first()
    if row:
        db.execute(text("""UPDATE ide_agent_runs SET status=:state
           WHERE tenant_id=:tenant AND id=:run AND status IN ('approved','running')"""),
           {"state":"completed" if success else "failed","tenant":tenant,"run":row.run_id})
    db.commit()
    return row is not None

def reserve_budget(db: Session, tenant: str, job: str, token: int, tokens: int, micro_usd: int) -> str:
    if not 1<=tokens<=2000 or not 1<=micro_usd<=5_000_000:
        raise ValueError("Invalid reservation")
    _scope(db, tenant)
    lease=db.execute(text("""SELECT 1 FROM ide_agent_jobs WHERE tenant_id=:tenant AND id=:job
       AND fencing_token=:token AND state='leased' AND lease_until>now() FOR UPDATE"""),
       {"tenant":tenant,"job":job,"token":token}).first()
    if lease is None:
        db.rollback()
        raise PermissionError("No valid fenced lease")
    existing=db.execute(text("""SELECT id FROM ide_agent_spend
       WHERE tenant_id=:tenant AND job_id=:job AND fencing_token=:token"""),
       {"tenant":tenant,"job":job,"token":token}).first()
    if existing:
        db.commit()
        return existing.id
    updated=db.execute(text("""UPDATE ide_agent_budgets
       SET reserved_tokens=reserved_tokens+:tokens,
           reserved_microusd=reserved_microusd+:cost
       WHERE tenant_id=:tenant AND spent_tokens+reserved_tokens+:tokens<=max_tokens
         AND spent_microusd+reserved_microusd+:cost<=max_cost_microusd
       RETURNING tenant_id"""),{"tenant":tenant,"tokens":tokens,"cost":micro_usd}).first()
    if updated is None:
        db.rollback()
        raise PermissionError("Tenant budget missing or exhausted")
    rid=str(uuid.uuid4())
    db.execute(text("""INSERT INTO ide_agent_spend
       (id,tenant_id,job_id,fencing_token,reserved_tokens,reserved_microusd)
       VALUES(:id,:tenant,:job,:token,:tokens,:cost)"""),
       {"id":rid,"tenant":tenant,"job":job,"token":token,"tokens":tokens,"cost":micro_usd})
    db.commit()
    return rid

def settle_budget(db: Session, tenant: str, reservation: str, actual_tokens: int, actual_micro_usd: int):
    if actual_tokens<0 or actual_micro_usd<0:
        raise ValueError("Invalid usage")
    _scope(db, tenant)
    row=db.execute(text("""SELECT reserved_tokens,reserved_microusd FROM ide_agent_spend
      WHERE tenant_id=:tenant AND id=:id AND state='reserved' FOR UPDATE"""),
      {"tenant":tenant,"id":reservation}).first()
    if row is None:
        db.rollback()
        raise ValueError("Reservation missing or already settled")
    if actual_tokens>row.reserved_tokens or actual_micro_usd>row.reserved_microusd:
        db.rollback()
        raise PermissionError("Actual usage exceeds reservation")
    db.execute(text("""UPDATE ide_agent_spend SET state='settled',
      actual_tokens=:tokens,actual_microusd=:cost WHERE tenant_id=:tenant AND id=:id"""),
      {"tenant":tenant,"id":reservation,"tokens":actual_tokens,"cost":actual_micro_usd})
    db.execute(text("""UPDATE ide_agent_budgets SET
      reserved_tokens=reserved_tokens-:reserved_tokens,
      reserved_microusd=reserved_microusd-:reserved_cost,
      spent_tokens=spent_tokens+:tokens,spent_microusd=spent_microusd+:cost
      WHERE tenant_id=:tenant"""),
      {"tenant":tenant,"reserved_tokens":row.reserved_tokens,
       "reserved_cost":row.reserved_microusd,"tokens":actual_tokens,"cost":actual_micro_usd})
    db.commit()
