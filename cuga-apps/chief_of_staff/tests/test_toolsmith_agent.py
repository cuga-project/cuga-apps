"""Tests for the LangGraph Toolsmith agent's deterministic fallback path.

The ReAct path requires an LLM and hits external services; we exercise
it in integration tests / live demos. The deterministic path proves the
end-to-end loop (catalog match → register OR openapi match → probe →
register) without any external dependencies.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from toolsmith.agent import Toolsmith  # noqa: E402
from toolsmith.artifact import ArtifactStore  # noqa: E402
from toolsmith.coders.base import CoderClient, CodeGenResult  # noqa: E402


class _StubCoder(CoderClient):
    name = "stub"
    async def generate_tool(self, spec):
        return CodeGenResult(code=f"# stub for {spec.name}\nasync def {spec.name}(**kw): return kw", notes="stub")
    async def revise_tool(self, prior, feedback):
        return prior


@pytest.fixture
def smith(tmp_path):
    store = ArtifactStore(tmp_path / "tools")
    return Toolsmith(coder=_StubCoder(), artifact_store=store, llm=False)


@pytest.mark.asyncio
async def test_catalog_path_creates_artifact(smith):
    """A gap that hits a curated MCP server in the catalog should result
    in a catalog-source artifact (no probe, no codegen)."""
    result = await smith.acquire({"capability": "wikipedia search"})
    assert result.success
    assert result.artifact_id
    artifact = smith.store.load(result.artifact_id)
    assert artifact is not None
    assert artifact.manifest.provenance.get("source") == "catalog"
    # Catalog mounts use the target name directly.
    assert artifact.manifest.name == "knowledge"


@pytest.mark.asyncio
async def test_openapi_path_probes_and_registers(smith, monkeypatch):
    """A gap that misses the catalog but matches OpenAPI should run a
    probe and only register on success."""
    from acquisition import probe as probe_mod

    async def fake_probe(realized, llm=None, timeout=None, auth=None, secrets=None):
        return {"ok": True, "status_code": 200, "response": {"name": "France"}, "reason": "ok"}

    monkeypatch.setattr(probe_mod, "probe_realized_tool", fake_probe)

    result = await smith.acquire({"capability": "country population currency"})
    assert result.success
    artifact = smith.store.load(result.artifact_id)
    assert artifact is not None
    assert artifact.manifest.provenance.get("source") == "openapi"
    assert artifact.last_probe and artifact.last_probe["ok"] is True
    # Coder ran — code should not be the empty fallback stub for HTTPError.
    assert "stub for" in artifact.code  # our stub coder's signature


@pytest.mark.asyncio
async def test_probe_failure_blocks_registration(smith, monkeypatch):
    from acquisition import probe as probe_mod

    async def failing_probe(realized, llm=None, timeout=None, auth=None, secrets=None):
        return {"ok": False, "reason": "http 404", "status_code": 404}

    monkeypatch.setattr(probe_mod, "probe_realized_tool", failing_probe)

    result = await smith.acquire({"capability": "country population currency"})
    assert result.success is False
    assert "404" in result.summary
    # Nothing should have been persisted.
    assert smith.list_artifacts() == []


@pytest.mark.asyncio
async def test_no_match_returns_failure(smith):
    result = await smith.acquire({"capability": "blockchain xyzzy quantum unicorn"})
    assert result.success is False
    assert "no" in result.summary.lower() or "miss" in result.summary.lower()


@pytest.mark.asyncio
async def test_remove_artifact(smith, monkeypatch):
    from acquisition import probe as probe_mod
    monkeypatch.setattr(probe_mod, "probe_realized_tool",
                        lambda *a, **kw: _ok_probe())
    # Use the catalog path which doesn't probe.
    result = await smith.acquire({"capability": "wikipedia search"})
    assert result.success
    assert result.artifact_id
    assert await smith.remove_artifact(result.artifact_id) is True
    assert smith.store.load(result.artifact_id) is None


async def _ok_probe(*_a, **_kw):
    return {"ok": True, "status_code": 200, "response": {"x": 1}, "reason": "ok"}
