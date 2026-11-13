from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import httpx
import os
import uuid
import hmac

app = FastAPI(title="AEP-X Registry Service", version="0.1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aepx:aepx_dev_only@postgres:5432/aepx")
IDENTITY_URL = os.getenv("IDENTITY_URL", "http://identity:8000")

try:
    import psycopg
    _PG_AVAILABLE = True
except Exception:
    _PG_AVAILABLE = False

# In-memory fallback so the service stays usable if Postgres is briefly
# unreachable (mirrors the aiplatform connector's degrade-don't-fail
# pattern) — state just won't survive a restart in that case.
_AGENTS: dict[str, dict] = {}


def _get_conn():
    if not _PG_AVAILABLE:
        if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
            raise RuntimeError("PostgreSQL driver unavailable in secure staging")
        return None
    try:
        return psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception as exc:
        if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
            raise RuntimeError("PostgreSQL connection unavailable in secure staging") from exc
        return None


class AgentIn(BaseModel):
    name: str
    organisation_id: str | None = None
    did: str | None = None


class Agent(AgentIn):
    id: str
    version: str = "0.0.1"
    trust_score: int = 0


def _mint_did() -> str | None:
    # Secure staging requires an authenticated Identity request and fails closed.
    try:
        resp = httpx.post(f"{IDENTITY_URL}/did", headers={"X-AEPX-Service-Key": os.getenv("AEPX_INTERNAL_SERVICE_KEY", "")} if os.getenv("AEPX_REQUIRE_DATABASE") == "true" else {}, timeout=3.0)
        resp.raise_for_status()
        return resp.json().get("did")
    except Exception as exc:
        if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
            raise HTTPException(503, "Identity service unavailable") from exc
        return None


@app.get("/health")
def health():
    conn = _get_conn()
    persisted = conn is not None
    if conn:
        conn.close()
    return {"status": "ok", "service": "registry", "persisted": persisted}


@app.post("/agents", response_model=Agent)
def create_agent(payload: AgentIn, x_aepx_service_key: str | None = Header(default=None)):
    if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
        expected = os.getenv("AEPX_INTERNAL_SERVICE_KEY", "")
        if len(expected) < 32 or not hmac.compare_digest(x_aepx_service_key or "", expected):
            raise HTTPException(403, "Service authentication required")
    if os.getenv("AEPX_REQUIRE_DATABASE") == "true" and payload.did is not None:
        raise HTTPException(403, "Externally supplied DIDs require verified ownership")
    did = payload.did or _mint_did()
    if os.getenv("AEPX_REQUIRE_DATABASE") == "true" and not did:
        raise HTTPException(503, "Identity service unavailable; registration blocked")
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agents (organisation_id, name, did) VALUES (%s, %s, %s) "
                    "RETURNING id, name, organisation_id, version, trust_score, did",
                    (payload.organisation_id, payload.name, did),
                )
                row = cur.fetchone()
            return Agent(id=str(row[0]), name=row[1], organisation_id=str(row[2]) if row[2] else None,
                         version=row[3], trust_score=row[4], did=row[5])
        except Exception:
            if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
                raise
            pass
        finally:
            conn.close()

    agent_id = str(uuid.uuid4())
    agent = Agent(id=agent_id, name=payload.name, organisation_id=payload.organisation_id, did=did)
    _AGENTS[agent_id] = agent.model_dump()
    return agent


@app.get("/agents/{agent_id}", response_model=Agent)
def get_agent(agent_id: str):
    try:
        uuid.UUID(agent_id)
    except (ValueError, AttributeError):
        raise HTTPException(404, "agent not found")
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, organisation_id, version, trust_score, did FROM agents WHERE id = %s",
                    (agent_id,),
                )
                row = cur.fetchone()
            if not row:
                raise HTTPException(404, "agent not found")
            return Agent(id=str(row[0]), name=row[1], organisation_id=str(row[2]) if row[2] else None,
                         version=row[3], trust_score=row[4], did=row[5])
        except HTTPException:
            raise
        except Exception:
            if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
                raise
            # e.g. agent_id isn't a valid UUID — no such agent, not a 500.
            raise HTTPException(404, "agent not found")
        finally:
            conn.close()

    if agent_id not in _AGENTS:
        raise HTTPException(404, "agent not found")
    return Agent(**_AGENTS[agent_id])


@app.get("/agents")
def list_agents():
    # Ordered by trust_score so any caller (e.g. the console's ranking
    # panel) gets a pre-ranked list for free.
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, organisation_id, version, trust_score, did FROM agents "
                    "ORDER BY trust_score DESC, name ASC"
                )
                rows = cur.fetchall()
            return [
                Agent(id=str(r[0]), name=r[1], organisation_id=str(r[2]) if r[2] else None,
                      version=r[3], trust_score=r[4], did=r[5])
                for r in rows
            ]
        except Exception:
            if os.getenv("AEPX_REQUIRE_DATABASE") == "true":
                raise
            pass
        finally:
            conn.close()

    return sorted(_AGENTS.values(), key=lambda a: (-a["trust_score"], a["name"]))
