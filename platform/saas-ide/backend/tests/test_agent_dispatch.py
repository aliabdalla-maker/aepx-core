"""Unit tests for the metered OpenRouter adapter and the dispatcher's isolation self-check."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("IDE_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("IDE_OIDC_ISSUER", "https://id.example.test")
os.environ.setdefault("IDE_OIDC_JWKS_URL", "https://id.example.test/keys")
os.environ.setdefault("IDE_OIDC_AUDIENCE", "ide-api")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import agent_dispatcher, providers
from app.metered_worker import build_prompt, daily_allowance, execute_next_metered


class FakeHTTP:
    def __init__(self, status=200, payload=None):
        self.status, self.payload, self.sent = status, payload or {}, None

    def post(self, url, json, headers):
        self.sent = (url, json, headers)
        return SimpleNamespace(status_code=self.status, json=lambda: self.payload)


@pytest.fixture
def live(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED", "IDE_NETWORK_ISOLATION_ATTESTED", "IDE_EGRESS_GATEWAY_VERIFIED"):
        monkeypatch.setenv(key, "true")
    monkeypatch.setenv("IDE_OPENROUTER_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def test_metered_call_returns_provider_cost_receipt(live):
    http = FakeHTTP(payload={"id": "gen-9", "model": "openai/gpt-4o-mini",
                             "choices": [{"message": {"content": "hello"}}],
                             "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0000123}})
    out = providers.generate_metered("openrouter", "hi", 100, system="sys", client=http)
    assert out == {"text": "hello", "model": "openai/gpt-4o-mini", "request_id": "gen-9",
                   "prompt_tokens": 10, "completion_tokens": 5, "cost_microusd": 12}
    url, body, headers = http.sent
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert body["usage"] == {"include": True} and body["max_tokens"] == 100
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert headers["Authorization"] == "Bearer test-key"


def test_metered_call_without_cost_reports_none(live):
    http = FakeHTTP(payload={"choices": [{"message": {"content": "x"}}], "usage": {"cost": "free"}})
    assert providers.generate_metered("openrouter", "hi", 10, client=http)["cost_microusd"] is None


def test_metered_call_fails_closed(live, monkeypatch):
    with pytest.raises(RuntimeError):
        providers.generate_metered("openrouter", "hi", 10, client=FakeHTTP(status=402))
    with pytest.raises(ValueError):
        providers.generate_metered("openrouter", "x" * 16001, 10, client=FakeHTTP())
    with pytest.raises(PermissionError):
        providers.generate_metered("openai", "hi", 10, client=FakeHTTP())
    monkeypatch.setenv("IDE_NETWORK_ISOLATION_ATTESTED", "false")
    http = FakeHTTP()
    with pytest.raises(PermissionError):
        providers.generate_metered("openrouter", "hi", 10, client=http)
    assert http.sent is None


def test_worker_gates_closed_by_default(monkeypatch):
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED", "IDE_GOVERNED_WORKER_ENABLED",
                "IDE_EGRESS_GATEWAY_VERIFIED", "IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(PermissionError):
        execute_next_metered("alpha", call=lambda *a, **k: pytest.fail("provider called"))
    for key in ("IDE_EXTERNAL_EXECUTION_ENABLED", "IDE_GOVERNED_WORKER_ENABLED", "IDE_EGRESS_GATEWAY_VERIFIED"):
        monkeypatch.setenv(key, "true")
    with pytest.raises(PermissionError, match="reconciliation"):
        execute_next_metered("alpha", call=lambda *a, **k: pytest.fail("provider called"))
    monkeypatch.setenv("IDE_PROVIDER_USAGE_RECONCILIATION_ENABLED", "true")
    monkeypatch.delenv("IDE_AI_MONTHLY_CAP_MICROUSD", raising=False)
    monkeypatch.setenv("IDE_WORKER_MAX_TOKENS", "100")
    monkeypatch.setenv("IDE_WORKER_MAX_MICROUSD", "1000")
    monkeypatch.setenv("IDE_WORKER_TIMEOUT_SECONDS", "5")
    with pytest.raises(ValueError, match="MONTHLY_CAP"):
        execute_next_metered("alpha", call=lambda *a, **k: pytest.fail("provider called"))


def test_plan_allowances_and_prompt(monkeypatch):
    assert daily_allowance("free") < daily_allowance("trial") < daily_allowance("pro")
    monkeypatch.setenv("IDE_AI_DAILY_MICROUSD_PRO", "5")
    assert daily_allowance("pro") == 5
    system, prompt = build_prompt('[{"agent":"composer","goal":"music"}]', "task")
    assert "- composer: music" in system and prompt == "task"
    assert build_prompt("not json", "t")[1] == "t"


class Conn:
    def close(self):
        pass


def test_isolation_attestation(monkeypatch):
    monkeypatch.delenv("IDE_NETWORK_ISOLATION_ATTESTED", raising=False)

    def internet_open(addr, timeout):
        return Conn()
    with pytest.raises(SystemExit, match="directly"):
        agent_dispatcher.attest_isolation(connect=internet_open)

    def no_gateway(addr, timeout):
        raise OSError("unreachable")
    with pytest.raises(SystemExit, match="gateway"):
        agent_dispatcher.attest_isolation(connect=no_gateway)
    assert os.getenv("IDE_NETWORK_ISOLATION_ATTESTED") is None

    def isolated(addr, timeout):
        if addr == ("gateway", 8080):
            return Conn()
        raise OSError("blocked")
    agent_dispatcher.attest_isolation(connect=isolated)
    assert os.environ["IDE_NETWORK_ISOLATION_ATTESTED"] == "true"
