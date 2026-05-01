"""Tests for the Toolsmith FastAPI service."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Force the artifact store to a tmp dir so tests don't pollute repo state.
    from toolsmith import artifact as artifact_mod
    monkeypatch.setattr(artifact_mod, "DEFAULT_TOOLS_DIR", tmp_path / "tools")

    # Disable the orchestration LLM and the Coder LLM defaults so the service
    # falls back to deterministic + stub paths.
    monkeypatch.setenv("TOOLSMITH_LLM_PROVIDER", "rits")
    monkeypatch.setenv("TOOLSMITH_LLM_MODEL", "no-such-model")
    monkeypatch.setenv("RITS_API_KEY", "")  # forces create_llm to fail → llm=None

    # Late import so the env / monkeypatches take effect.
    from toolsmith import server as server_mod
    importlib_reload(server_mod)
    return server_mod.app


def importlib_reload(mod):
    import importlib
    importlib.reload(mod)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "coder" in body
    assert "artifact_count" in body


def test_tools_initially_empty(client):
    r = client.get("/tools")
    assert r.status_code == 200
    assert r.json() == []


def test_acquire_no_match_returns_failure(client):
    r = client.post("/acquire", json={"gap": {"capability": "blockchain xyzzy quantum gibberish"}})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["artifact_id"] is None


def test_acquire_catalog_path(client):
    """Wikipedia gap should match the catalog 'knowledge' entry; deterministic
    path mounts it without probing."""
    r = client.post("/acquire", json={"gap": {"capability": "wikipedia search"}})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["artifact_id"]

    # /tools should now list the artifact.
    r2 = client.get("/tools")
    assert any(t["id"] == body["artifact_id"] for t in r2.json())


def test_get_tool_by_id(client):
    r = client.post("/acquire", json={"gap": {"capability": "wikipedia search"}})
    artifact_id = r.json()["artifact_id"]

    r2 = client.get(f"/tools/{artifact_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert "code" in body
    assert "mcp_tool_spec" in body


def test_delete_tool(client):
    r = client.post("/acquire", json={"gap": {"capability": "wikipedia search"}})
    artifact_id = r.json()["artifact_id"]

    r2 = client.delete(f"/tools/{artifact_id}")
    assert r2.status_code == 200
    assert r2.json()["removed"] is True

    r3 = client.get(f"/tools/{artifact_id}")
    assert r3.status_code == 404


def test_effective_state_splits_catalog_from_extra_tools(client):
    # Catalog entry → contributes to mcp_servers.
    client.post("/acquire", json={"gap": {"capability": "wikipedia search"}})

    r = client.get("/effective_state")
    body = r.json()
    assert "knowledge" in body["mcp_servers"]
    assert body["extra_tools"] == []


def test_all_artifact_specs_returns_mcp_specs(client):
    client.post("/acquire", json={"gap": {"capability": "wikipedia search"}})
    r = client.get("/specs/all_artifacts")
    specs = r.json()
    assert len(specs) == 1
    assert "tool_name" in specs[0]
    assert "code" in specs[0]
