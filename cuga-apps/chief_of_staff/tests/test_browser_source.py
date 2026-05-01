"""Tests for the BrowserSource plugin and Toolsmith's browser routing."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from acquisition.sources.browser_source import BrowserSource  # noqa: E402


@pytest.fixture
def source():
    return BrowserSource()


@pytest.mark.asyncio
async def test_browser_source_loads_curated_tasks(source):
    ids = {t.id for t in source._tasks}
    assert "hn_top_stories" in ids
    assert "wikipedia_search" in ids
    assert "github_repo_about" in ids


@pytest.mark.asyncio
async def test_match_hacker_news(source):
    proposals = await source.propose({"capability": "hacker news top stories"})
    assert len(proposals) > 0
    assert proposals[0].id == "browser:hn_top_stories"


@pytest.mark.asyncio
async def test_match_school_portal_picks_template(source):
    proposals = await source.propose({"capability": "check kids grades on school portal"})
    ids = [p.id for p in proposals]
    assert "browser:school_portal_grades" in ids


@pytest.mark.asyncio
async def test_school_portal_proposal_declares_secrets(source):
    proposals = await source.propose({"capability": "school portal grades"})
    p = next(p for p in proposals if p.id == "browser:school_portal_grades")
    assert "school_portal_username" in p.auth
    assert "school_portal_password" in p.auth


@pytest.mark.asyncio
async def test_realize_returns_browser_task_shape(source):
    proposals = await source.propose({"capability": "hacker news top stories"})
    realized = await source.realize(proposals[0])
    assert realized.tool_name == "hn_top_stories"
    assert realized.invoke_url is None
    assert realized.requires_secrets == []


@pytest.mark.asyncio
async def test_realize_unknown_id_raises(source):
    from acquisition.sources.base import Proposal
    fake = Proposal(
        id="browser:nope", name="x", description="", capabilities=[],
        source="browser", score=0.0, spec={"task_id": "nope"},
    )
    with pytest.raises(ValueError):
        await source.realize(fake)


# ─── Toolsmith routing ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_toolsmith_routes_to_browser_when_apis_miss(tmp_path, monkeypatch):
    """A capability that only the browser source can fill should route
    through _acquire_browser, not the OpenAPI path."""
    from toolsmith.agent import Toolsmith
    from toolsmith.artifact import ArtifactStore
    from toolsmith.coders.base import CoderClient, CodeGenResult

    class _StubCoder(CoderClient):
        name = "stub"
        async def generate_tool(self, spec): return CodeGenResult(code="")
        async def revise_tool(self, prior, feedback): return prior

    smith = Toolsmith(
        coder=_StubCoder(),
        artifact_store=ArtifactStore(tmp_path / "tools"),
        llm=False,
    )

    # Mock the browser-runner probe response so we don't try to hit a real one.
    import httpx
    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "reason": "mock probe"}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    result = await smith.acquire({"capability": "hacker news top stories"})
    assert result.success, result.summary
    artifact = smith.store.load(result.artifact_id)
    assert artifact is not None
    assert artifact.manifest.kind == "browser_task"
    assert artifact.manifest.steps  # non-empty steps list


@pytest.mark.asyncio
async def test_toolsmith_browser_blocks_on_missing_secrets(tmp_path):
    """School portal browser task needs username + password — Toolsmith
    should return needs_secrets, not register the artifact."""
    from toolsmith.agent import Toolsmith
    from toolsmith.artifact import ArtifactStore
    from toolsmith.coders.base import CoderClient, CodeGenResult

    class _StubCoder(CoderClient):
        name = "stub"
        async def generate_tool(self, spec): return CodeGenResult(code="")
        async def revise_tool(self, prior, feedback): return prior

    smith = Toolsmith(
        coder=_StubCoder(),
        artifact_store=ArtifactStore(tmp_path / "tools"),
        llm=False,
    )
    result = await smith.acquire({"capability": "check kids grades school portal"})
    assert result.success is False
    assert result.needs_secrets is not None
    assert "school_portal_username" in result.needs_secrets["missing"]


@pytest.mark.asyncio
async def test_toolsmith_unknown_gap_returns_no_match(tmp_path):
    """Things no source can do should still fail cleanly with the new
    'No catalog, OpenAPI, or browser-task match' message."""
    from toolsmith.agent import Toolsmith
    from toolsmith.artifact import ArtifactStore
    from toolsmith.coders.base import CoderClient, CodeGenResult

    class _StubCoder(CoderClient):
        name = "stub"
        async def generate_tool(self, spec): return CodeGenResult(code="")
        async def revise_tool(self, prior, feedback): return prior

    smith = Toolsmith(
        coder=_StubCoder(),
        artifact_store=ArtifactStore(tmp_path / "tools"),
        llm=False,
    )
    result = await smith.acquire({"capability": "blockchain xyzzy quantum unicorn forge"})
    assert not result.success
    assert "browser-task" in result.summary or "No catalog" in result.summary
