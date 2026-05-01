"""End-to-end auth flow: needs_secrets surfaces, vault put unblocks."""

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
        # Echo back the secret name so we can verify it's threaded through.
        sig_extras = ", ".join(spec.requires_secrets)
        sig = f"({', '.join(spec.parameters_schema or {})}{', ' + sig_extras if sig_extras else ''})"
        return CodeGenResult(
            code=f"async def {spec.name}{sig}: return {{'auth_param': '{sig_extras}'}}",
        )
    async def revise_tool(self, prior, feedback): return prior


@pytest.fixture
def smith(tmp_path):
    store = ArtifactStore(tmp_path / "tools")
    return Toolsmith(coder=_StubCoder(), artifact_store=store, llm=False)


@pytest.mark.asyncio
async def test_github_search_blocks_on_missing_secret(smith):
    """A gap that matches an auth-required API should return needs_secrets,
    not build anything."""
    result = await smith.acquire({"capability": "github search repositories"})
    assert result.success is False
    assert result.needs_secrets is not None
    assert "github_token" in result.needs_secrets["missing"]
    # Nothing got persisted.
    assert smith.list_artifacts() == []


@pytest.mark.asyncio
async def test_secret_put_then_acquire_succeeds(smith, monkeypatch):
    """After putting the secret in the vault, the acquire should pass through
    auth check, run the probe (mocked here), and register."""
    from acquisition import probe as probe_mod

    async def fake_probe(realized, llm=None, timeout=None, auth=None, secrets=None):
        # The probe should receive the secret value.
        assert secrets and "github_token" in secrets
        return {"ok": True, "status_code": 200, "response": {"items": [{"id": 1}]}, "reason": "ok"}

    monkeypatch.setattr(probe_mod, "probe_realized_tool", fake_probe)

    # First attempt — blocked.
    r1 = await smith.acquire({"capability": "github search repositories"})
    assert r1.success is False
    tool_id = r1.needs_secrets["tool_id"]

    # User submits the secret.
    smith.vault.put(tool_id, "github_token", "ghp_abc123")

    # Retry — should succeed and persist.
    r2 = await smith.acquire({"capability": "github search repositories"})
    assert r2.success is True
    assert r2.artifact_id == tool_id

    artifact = smith.store.load(tool_id)
    assert artifact is not None
    assert artifact.manifest.requires_secrets == ["github_token"]
    assert "github_token" in artifact.code  # coder added the auth kwarg


@pytest.mark.asyncio
async def test_no_auth_api_unaffected(smith, monkeypatch):
    """Auth handling shouldn't break the no-auth path (jokes, countries)."""
    from acquisition import probe as probe_mod

    async def ok_probe(realized, llm=None, timeout=None, auth=None, secrets=None):
        return {"ok": True, "status_code": 200, "response": {"setup": "x", "punchline": "y"}, "reason": "ok"}

    monkeypatch.setattr(probe_mod, "probe_realized_tool", ok_probe)
    result = await smith.acquire({"capability": "random joke"})
    assert result.success
    assert result.needs_secrets is None
