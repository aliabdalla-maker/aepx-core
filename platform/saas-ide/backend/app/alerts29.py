"""Tenant-scoped read-only operational alerts; caller must authorize tenant first."""
from .recovery25 import tenant_metrics

def evaluate_tenant_alerts(db, tenant: str, *, max_failed: int=0,
                           max_unresolved: int=0, spend_percent: int=80) -> list[dict]:
    if min(max_failed,max_unresolved)<0 or not 1<=spend_percent<=100:
        raise ValueError("Invalid alert thresholds")
    metrics=tenant_metrics(db,tenant)
    alerts=[]
    failed=metrics["jobs"].get("failed",0)
    if failed>max_failed:
        alerts.append({"tenant":tenant,"code":"failed_jobs","count":failed})
    unresolved=metrics["unresolved_reservations"]
    if unresolved>max_unresolved:
        alerts.append({"tenant":tenant,"code":"unresolved_reservations","count":unresolved})
    budget=metrics["budget"]
    if budget and budget["max_cost_microusd"]>0:
        usage=budget["spent_microusd"]+budget["reserved_microusd"]
        if usage*100>=spend_percent*budget["max_cost_microusd"]:
            alerts.append({"tenant":tenant,"code":"budget_threshold","percent":usage*100//budget["max_cost_microusd"]})
    return alerts
