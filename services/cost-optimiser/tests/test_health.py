from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.json() == {"status": "ok", "service": "cost-optimiser"}


def test_decide_returns_utility_score():
    mock_response = AsyncMock()
    mock_response.json = lambda: {"trust_score": 80}
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        resp = client.post(
            "/route/decide",
            json={
                "agent_id": "agent-1",
                "capability": "lesson_generation",
                "candidate_route": "cache",
                "estimated_cost": 0.0,
                "estimated_latency_ms": 5,
                "estimated_energy": 0.0,
            },
        )
    assert "utility_score" in resp.json()
