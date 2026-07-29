import fakeredis
from fastapi.testclient import TestClient
import app.main as main

main.r = fakeredis.FakeRedis(decode_responses=True)
client = TestClient(main.app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "discovery"}


def test_score_prefers_higher_trust():
    agent = {"confidence": 0.8, "latency_ms": 50, "cost": 0.0}
    high_trust = main.score(agent, {"trust_score": 90})
    low_trust = main.score(agent, {"trust_score": 10})
    assert high_trust > low_trust
