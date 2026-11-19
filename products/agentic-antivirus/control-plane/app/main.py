"""Agentic Antivirus control plane (FastAPI). OpenAPI at /v1/openapi.json (BE-01, DLV-05)."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import db, governance, licensing
from app.routers import (actions, agent, auth, billing, endpoints, files, incidents, integrations, investigation,
                         platform, threats)

app = FastAPI(title="Agentic Antivirus Control Plane", version="0.1.0", openapi_url="/v1/openapi.json",
              docs_url="/v1/docs")

for r in (auth.router, agent.router, endpoints.router, incidents.router, actions.router, investigation.router,
          integrations.router, threats.router, billing.router, files.router, platform.router):
    app.include_router(r)

# Paths that stay reachable when the console is paywalled (post-trial policy) so users can
# sign in, read help/privacy, see their licence, and pay.
_LICENCE_EXEMPT = ("/v1/auth", "/v1/licence", "/v1/billing", "/v1/ads", "/v1/agent", "/v1/ingest", "/v1/i18n",
                   "/v1/tenants", "/health", "/ready", "/v1/openapi.json", "/v1/docs")


@app.middleware("http")
async def trace_and_licence(request: Request, call_next):
    trace_id = request.headers.get("traceparent") or uuid.uuid4().hex
    path = request.url.path
    tenant = request.headers.get("x-tenant-id")
    if tenant and path.startswith("/v1/") and not path.startswith(_LICENCE_EXEMPT):
        try:
            with db.tenant_tx(uuid.UUID(tenant)) as cur:
                cur.execute("SELECT 1 FROM aav.subscriptions")
                if cur.fetchone():
                    ent = licensing.entitlement(cur, tenant_id=tenant)
                    if not ent["console_access"]:
                        return JSONResponse({"detail": "subscription required", "entitlement": ent}, status_code=402)
        except ValueError:
            pass  # malformed tenant id: the route's own dependency returns 400
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
def health():
    """Liveness."""
    return {"status": "ok", "service": "agentic-antivirus-control-plane"}


@app.get("/ready")
def ready():
    """Readiness gate (OCI-13): database, AEP-X governance, signing key, detection bundle."""
    checks = {}
    try:
        with db.global_tx() as cur:
            cur.execute("SELECT 1 AS ok")
            checks["database"] = cur.fetchone()["ok"] == 1
    except Exception as exc:  # pragma: no cover - exercised when DB is down
        checks["database"] = f"error: {type(exc).__name__}"
    gov = governance.evaluate("S0")
    checks["aepx_governance"] = gov["allowed"] or gov["reason"]
    try:
        from app import crypto
        checks["signing_key"] = bool(crypto.key_id())
    except Exception as exc:
        checks["signing_key"] = f"error: {exc}"
    try:
        from app.detections import current_engine
        eng = current_engine()
        checks["detection_bundle"] = eng.version if eng else "none published"
    except Exception as exc:  # pragma: no cover
        checks["detection_bundle"] = f"error: {type(exc).__name__}"
    ok = checks["database"] is True and checks["aepx_governance"] is True and checks["signing_key"] is True
    return JSONResponse({"ready": ok, "checks": checks}, status_code=200 if ok else 503)
