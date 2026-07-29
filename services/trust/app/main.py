from fastapi import FastAPI
from pydantic import BaseModel
import os

app = FastAPI(title="AEP-X Trust Service", version="0.1.0")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://aepx:aepx_dev_only@postgres:5432/aepx")
_COMPONENTS = ["identity_score", "behaviour_score", "security_score", "evidence_score", "reputation_score"]
_DEFAULT = 50

try:
    import psycopg
    _PG_AVAILABLE = True
except Exception:
    _PG_AVAILABLE = False

# Fallback store so a Postgres blip degrades to stateless-but-working
# rather than a hard failure — mirrors the aiplatform connector's pattern.
_FALLBACK: dict[str, dict] = {}


def _get_conn():
    if not _PG_AVAILABLE:
        return None
    try:
        return psycopg.connect(DATABASE_URL, connect_timeout=3)
    except Exception:
        return None


def _level_for(score: int) -> str:
    # RFC-0002 trust levels.
    if score >= 90:
        return "Trusted"
    if score >= 60:
        return "Verified"
    if score >= 30:
        return "Provisional"
    return "Untrusted"


class AdjustIn(BaseModel):
    component: str  # one of _COMPONENTS, without the "_score" suffix also accepted
    delta: int


def _normalise_component(name: str) -> str:
    return name if name.endswith("_score") else f"{name}_score"


@app.get("/health")
def health():
    conn = _get_conn()
    persisted = conn is not None
    if conn:
        conn.close()
    return {"status": "ok", "service": "trust", "persisted": persisted}


def _row_to_dict(entity_id: str, row) -> dict:
    scores = dict(zip(_COMPONENTS, row))
    total = round(sum(scores.values()) / len(scores))
    return {"entity_id": entity_id, "trust_score": total, "level": _level_for(total), **scores}


@app.get("/trust/{entity_id}")
def get_trust(entity_id: str, entity_type: str = "agent"):
    # RFC-0002 5-component formula: identity, behaviour, security, evidence,
    # reputation — averaged into a single 0-100 score. Fetch-or-create so
    # any never-seen-before entity gets a sane default row rather than 404.
    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(_COMPONENTS)} FROM trust_scores WHERE entity_id = %s",
                    (entity_id,),
                )
                row = cur.fetchone()
                if not row:
                    defaults = [_DEFAULT] * len(_COMPONENTS)
                    cur.execute(
                        "INSERT INTO trust_scores (entity_id, entity_type, identity_score, behaviour_score, "
                        "security_score, evidence_score, reputation_score) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (entity_id, entity_type, *defaults),
                    )
                    row = tuple(defaults)
            return _row_to_dict(entity_id, row)
        except Exception:
            # A query-level error (not just "no connection") must degrade
            # the same way — a bad row must never 500 the Connector Bus's
            # trust check for every agent behind it.
            pass
        finally:
            conn.close()

    if entity_id not in _FALLBACK:
        _FALLBACK[entity_id] = {c: _DEFAULT for c in _COMPONENTS}
    return _row_to_dict(entity_id, tuple(_FALLBACK[entity_id][c] for c in _COMPONENTS))


@app.post("/trust/{entity_id}/adjust")
def adjust_trust(entity_id: str, payload: AdjustIn):
    # Internal signal endpoint — e.g. the Connector Bus nudges behaviour_score
    # up on a successful invocation, so trust reflects real usage over time
    # instead of sitting at a flat default forever.
    component = _normalise_component(payload.component)
    if component not in _COMPONENTS:
        return {"error": f"unknown component '{payload.component}'"}

    conn = _get_conn()
    if conn:
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT {', '.join(_COMPONENTS)} FROM trust_scores WHERE entity_id = %s FOR UPDATE",
                    (entity_id,),
                )
                row = cur.fetchone()
                if not row:
                    row = tuple(_DEFAULT for _ in _COMPONENTS)
                    cur.execute(
                        "INSERT INTO trust_scores (entity_id, entity_type, identity_score, behaviour_score, "
                        "security_score, evidence_score, reputation_score) VALUES (%s, 'agent', %s, %s, %s, %s, %s)",
                        (entity_id, *row),
                    )
                scores = dict(zip(_COMPONENTS, row))
                scores[component] = max(0, min(100, scores[component] + payload.delta))
                cur.execute(
                    f"UPDATE trust_scores SET {component} = %s, updated_at = now() WHERE entity_id = %s",
                    (scores[component], entity_id),
                )
            return _row_to_dict(entity_id, tuple(scores.values()))
        except Exception:
            pass
        finally:
            conn.close()

    if entity_id not in _FALLBACK:
        _FALLBACK[entity_id] = {c: _DEFAULT for c in _COMPONENTS}
    _FALLBACK[entity_id][component] = max(0, min(100, _FALLBACK[entity_id][component] + payload.delta))
    return _row_to_dict(entity_id, tuple(_FALLBACK[entity_id][c] for c in _COMPONENTS))
