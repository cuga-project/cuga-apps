"""Smoke test — boots the FastAPI backend and round-trips /chat through the stub planner."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from main import app  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    # Both downstream services unreachable → the orchestrator's stub
    # fallback paths kick in. This validates the wiring without needing
    # cuga or the toolsmith service running.
    monkeypatch.setenv("CUGA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("TOOLSMITH_URL", "http://127.0.0.1:1")
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "tools_registered" in body
    assert "toolsmith" in body


def test_chat_echoes_when_planner_unreachable(client):
    r = client.post("/chat", json={"message": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert "hello" in body["response"]
    assert body["thread_id"] == "default"
    assert body["acquisition"] is None  # no gap, no acquisition triggered


def test_tools_endpoint_returns_list(client):
    r = client.get("/tools")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_artifacts_endpoint_returns_list(client):
    r = client.get("/toolsmith/artifacts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_artifacts_changed_webhook(client):
    # Fires a resync; with both services unreachable it gracefully fails
    # but the endpoint must still return 200 (or a structured error).
    r = client.post("/internal/artifacts_changed")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
