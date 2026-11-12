"""Fail-closed reconciliation and lease recovery.

External calls are not replayed automatically: ambiguous delivery is quarantined.
Only a separately authenticated operator may invoke reconciliation.
"""
import uuid
from sqlalchemy import text
from .phase23 import _scope

def quarantine_expired(db, tenant: str, *, limit: int = 50) -> int:
    if not 1<=limit<=100:
        raise ValueError("Invalid batch size")
    _scope(db,tenant)
    rows=db.execute(text("""SELECT j.id,j.run_id FROM ide_agent_jobs j
      WHERE j.tenant_id=:tenant AND j.state='leased' AND j.lease_until<now()
      ORDER BY j.lease_until FOR UPDATE SKIP LOCKED LIMIT :limit"""),
      {"tenant":tenant,"limit":limit}).all()
    for job,run in rows:
        db.execute(text("""UPDATE ide_agent_jobs SET state='failed',fencing_token=fencing_token+1,
          lease_owner=NULL,lease_until=NULL,completed_at=now()
          WHERE tenant_id=:tenant AND id=:job"""),{"tenant":tenant,"job":job})
        db.execute(text("""UPDATE ide_agent_runs SET status='failed'
          WHERE tenant_id=:tenant AND id=:run AND status IN ('approved','running')"""),
          {"tenant":tenant,"run":run})
        db.execute(text("""INSERT INTO ide_agent_audit(id,tenant_id,run_id,actor,action)
          VALUES(:id,:tenant,:run,'system:recovery','lease_quarantined')"""),
          {"id":str(uuid.uuid4()),"tenant":tenant,"run":run})
    db.commit()
    return len(rows)

def reconcile(db, tenant: str, reservation: str, reference: str,
              tokens: int, microusd: int, *, actor: str) -> None:
    if not actor or not reference or len(reference)>160 or tokens<0 or microusd<0:
        raise ValueError("Invalid reconciliation evidence")
    _scope(db,tenant)
    row=db.execute(text("""SELECT s.job_id,s.state,s.reserved_tokens,s.reserved_microusd,
      s.actual_tokens,s.actual_microusd,j.run_id FROM ide_agent_spend s
      JOIN ide_agent_jobs j ON j.tenant_id=s.tenant_id AND j.id=s.job_id
      WHERE s.tenant_id=:tenant AND s.id=:reservation FOR UPDATE OF s"""),
      {"tenant":tenant,"reservation":reservation}).first()
    if row is None:
        db.rollback()
        raise LookupError("Reservation not found")
    if row.state=="released":
        db.rollback()
        raise PermissionError("Released reservation requires manual investigation")
    if tokens>row.reserved_tokens or microusd>row.reserved_microusd:
        db.rollback()
        raise PermissionError("Provider usage exceeds reserved envelope: manual investigation required")
    existing=db.execute(text("""SELECT provider_reference FROM ide_agent_reconciliation
      WHERE tenant_id=:tenant AND reservation_id=:reservation"""),
      {"tenant":tenant,"reservation":reservation}).first()
    if existing:
        db.rollback()
        raise ValueError("Reservation already reconciled")
    old_tokens=row.actual_tokens if row.state=="settled" else 0
    old_cost=row.actual_microusd if row.state=="settled" else 0
    db.execute(text("""UPDATE ide_agent_budgets SET
      reserved_tokens=reserved_tokens-:rt,
      reserved_microusd=reserved_microusd-:rc,
      spent_tokens=spent_tokens+:tokens-:old_tokens,
      spent_microusd=spent_microusd+:cost-:old_cost
      WHERE tenant_id=:tenant AND spent_tokens+:tokens-:old_tokens>=0
        AND spent_microusd+:cost-:old_cost>=0"""),
      {"tenant":tenant,"rt":row.reserved_tokens if row.state=="reserved" else 0,
       "rc":row.reserved_microusd if row.state=="reserved" else 0,
       "tokens":tokens,"cost":microusd,"old_tokens":old_tokens,"old_cost":old_cost})
    db.execute(text("""UPDATE ide_agent_spend SET state='settled',actual_tokens=:tokens,
      actual_microusd=:cost,reconciled_at=now(),reconciliation_reference=:reference
      WHERE tenant_id=:tenant AND id=:reservation"""),
      {"tenant":tenant,"reservation":reservation,"tokens":tokens,"cost":microusd,"reference":reference})
    db.execute(text("""INSERT INTO ide_agent_reconciliation
      (id,tenant_id,reservation_id,provider_reference,actual_tokens,actual_microusd,actor)
      VALUES(:id,:tenant,:reservation,:reference,:tokens,:cost,:actor)"""),
      {"id":str(uuid.uuid4()),"tenant":tenant,"reservation":reservation,
       "reference":reference,"tokens":tokens,"cost":microusd,"actor":actor})
    db.execute(text("""INSERT INTO ide_agent_audit(id,tenant_id,run_id,actor,action)
      VALUES(:id,:tenant,:run,:actor,'usage_reconciled')"""),
      {"id":str(uuid.uuid4()),"tenant":tenant,"run":row.run_id,"actor":actor})
    db.commit()

def tenant_metrics(db, tenant: str) -> dict:
    _scope(db,tenant)
    budget=db.execute(text("""SELECT max_tokens,max_cost_microusd,reserved_tokens,
      reserved_microusd,spent_tokens,spent_microusd FROM ide_agent_budgets
      WHERE tenant_id=:tenant"""),{"tenant":tenant}).mappings().first()
    jobs=db.execute(text("""SELECT state,count(*) AS total FROM ide_agent_jobs
      WHERE tenant_id=:tenant GROUP BY state"""),{"tenant":tenant}).all()
    stranded=db.execute(text("""SELECT count(*) FROM ide_agent_spend s
      JOIN ide_agent_jobs j ON j.tenant_id=s.tenant_id AND j.id=s.job_id
      WHERE s.tenant_id=:tenant AND s.state='reserved' AND
      (j.state IN ('failed','cancelled','completed') OR
       (j.state='leased' AND j.lease_until<now()))"""),{"tenant":tenant}).scalar()
    result={"budget":dict(budget) if budget else None,
            "jobs":{state:count for state,count in jobs},"unresolved_reservations":stranded}
    db.rollback()
    return result
