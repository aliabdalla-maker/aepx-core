from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import uuid

app = FastAPI(title="AEP-X Registry Service", version="0.1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aepx:aepx_dev_only@postgres:5432/aepx")

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
        return None
    try:
        return psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception:
        return None


class AgentIn(BaseModel):
    name: str
    organisation_id: str | None = None


class Agent(AgentIn):
    id: str
    version: str = "0.0.1"
    trust_score: int = 0


@app.get("/health")
def health():
    conn = _get_conn()
    persisted = conn is not None
    if conn:
        conn.close()
    return {"status": "ok", "service": "registry", "persisted": persisted}


@app.post("/agents", response_model=Agent)
def create_agent(payload: AgentIn):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO agents (organisation_id, name) VALUES (%s, %s) "
                    "RETURNING id, name, organisation_id, version, trust_score",
                    (payload.organisation_id, payload.name),
                )
                row = cur.fetchone()
            return Agent(id=str(row[0]), name=row[1], organisation_id=str(row[2]) if row[2] else None,
                         version=row[3], trust_score=row[4])
        except Exception:
            pass
        finally:
            conn.close()

    agent_id = str(uuid.uuid4())
    agent = Agent(id=agent_id, **payload.model_dump())
    _AGENTS[agent_id] = agent.model_dump()
    return agent


@app.get("/agents/{agent_id}", response_model=Agent)
def get_agent(agent_id: str):
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name, organisation_id, version, trust_score FROM agents WHERE id = %s",
                    (agent_id,),
                )
                row = cur.fetchone()
            if not row:
                raise HTTPException(404, "agent not found")
            return Agent(id=str(row[0]), name=row[1], organisation_id=str(row[2]) if row[2] else None,
                         version=row[3], trust_score=row[4])
        except HTTPException:
            raise
        except Exception:
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
                    "SELECT id, name, organisation_id, version, trust_score FROM agents "
                    "ORDER BY trust_score DESC, name ASC"
                )
                rows = cur.fetchall()
            return [
                Agent(id=str(r[0]), name=r[1], organisation_id=str(r[2]) if r[2] else None,
                      version=r[3], trust_score=r[4])
                for r in rows
            ]
        except Exception:
            pass
        finally:
            conn.close()

    return sorted(_AGENTS.values(), key=lambda a: (-a["trust_score"], a["name"]))
