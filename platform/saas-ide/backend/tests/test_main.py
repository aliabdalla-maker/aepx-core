import importlib
import os

from fastapi.testclient import TestClient


def test_fail_closed_and_tenant_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("IDE_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("IDE_ENV", "development")
    monkeypatch.setenv("IDE_DEV_API_KEY", "local-test-secret")
    from app import main
    importlib.reload(main)
    client = TestClient(main.app)

    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/projects", headers={
        "x-ide-tenant": "alpha", "x-ide-api-key": "wrong"
    }).status_code == 401

    a = {"x-ide-tenant": "alpha", "x-ide-api-key": "local-test-secret"}
    b = {"x-ide-tenant": "beta", "x-ide-api-key": "local-test-secret"}
    created = client.post("/api/v1/projects", headers=a, json={
        "name": "First project", "description": "Tenant scoped"
    })
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert len(client.get("/api/v1/projects", headers=a).json()) == 1
    assert client.get("/api/v1/projects", headers=b).json() == []
    assert client.get(f"/api/v1/projects/{project_id}", headers=b).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}", headers=a).status_code == 200

    monkeypatch.setenv("IDE_ENV", "production")
    assert client.get("/api/v1/projects", headers=a).status_code == 503
