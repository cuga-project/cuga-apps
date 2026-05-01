"""Tests for phase 3.8: probe_executed_code + Toolsmith revise loop."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from acquisition.probe import probe_executed_code  # noqa: E402
from toolsmith.agent import Toolsmith  # noqa: E402
from toolsmith.artifact import ArtifactStore  # noqa: E402
from toolsmith.coders.base import CoderClient, CodeGenResult  # noqa: E402


# ─── probe_executed_code ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_executed_probe_passes_for_valid_code():
    code = """
async def hello(name):
    return {'greeting': 'hi ' + name}
"""
    result = await probe_executed_code(code, "hello", {"name": "world"})
    assert result["ok"]
    assert result["response"] == {"greeting": "hi world"}


@pytest.mark.asyncio
async def test_executed_probe_rejects_disallowed_import():
    code = """
import subprocess
async def boom():
    return subprocess.check_output(['id'])
"""
    result = await probe_executed_code(code, "boom", {})
    assert not result["ok"]
    assert "disallowed import" in result["reason"]


@pytest.mark.asyncio
async def test_executed_probe_catches_runtime_error():
    code = """
async def divide():
    return 1 / 0
"""
    result = await probe_executed_code(code, "divide", {})
    assert not result["ok"]
    assert "runtime error" in result["reason"] or "ZeroDivisionError" in result["reason"]


@pytest.mark.asyncio
async def test_executed_probe_rejects_empty_payload():
    code = """
async def empty():
    return []
"""
    result = await probe_executed_code(code, "empty", {})
    assert not result["ok"]
    assert "empty" in result["reason"]


@pytest.mark.asyncio
async def test_executed_probe_signature_mismatch():
    code = """
async def needs_x(x):
    return {'x': x}
"""
    # Sample input passes 'y' instead of 'x' → TypeError
    result = await probe_executed_code(code, "needs_x", {"y": 1})
    assert not result["ok"]
    assert "signature mismatch" in result["reason"]


# ─── Toolsmith revise loop ───────────────────────────────────────────────

class _RevisingCoder(CoderClient):
    """Stub Coder that emits broken code on first generate, fixes it on revise."""
    name = "revising_stub"

    def __init__(self):
        self.generate_count = 0
        self.revise_count = 0

    async def generate_tool(self, spec):
        self.generate_count += 1
        # First version is intentionally broken: returns None (which probe rejects).
        sig_extras = ", ".join(spec.requires_secrets)
        sig = f"({', '.join(spec.parameters_schema or {})}{', ' + sig_extras if sig_extras else ''})"
        return CodeGenResult(code=f"async def {spec.name}{sig}: return None\n")

    async def revise_tool(self, prior, feedback):
        self.revise_count += 1
        # The fix: replace the body. Find the def line, append a fixed body.
        sig_line = prior.code.split(":", 1)[0]  # everything up to the first colon
        return CodeGenResult(code=f"{sig_line}:\n    return {{'fixed': True}}\n")


@pytest.fixture
def smith(tmp_path):
    return Toolsmith(
        coder=_RevisingCoder(),
        artifact_store=ArtifactStore(tmp_path / "tools"),
        llm=False,
    )


@pytest.mark.asyncio
async def test_revise_loop_fixes_broken_code(smith, monkeypatch):
    """First generation returns None (probe fails); revise produces valid
    code; the artifact ends up with the fixed code and revisions recorded."""
    from acquisition import probe as probe_mod

    async def url_probe(realized, llm=None, timeout=None, auth=None, secrets=None):
        return {"ok": True, "status_code": 200, "response": {"data": [1]}, "reason": "url ok"}

    monkeypatch.setattr(probe_mod, "probe_realized_tool", url_probe)

    result = await smith.acquire({"capability": "country population currency"})
    assert result.success, f"expected success after revision, got: {result.summary}"

    artifact = smith.store.load(result.artifact_id)
    assert artifact is not None
    assert "{'fixed': True}" in artifact.code
    revisions = artifact.manifest.provenance.get("revisions") or []
    # First attempt failed, second attempt passed → 2 entries.
    assert len(revisions) == 2
    assert revisions[0]["ok"] is False
    assert revisions[1]["ok"] is True


@pytest.mark.asyncio
async def test_revise_loop_gives_up_after_max_attempts(monkeypatch, tmp_path):
    """Coder that NEVER fixes the code → loop bounded at _MAX_REVISIONS."""
    from acquisition import probe as probe_mod
    from toolsmith.agent import _MAX_REVISIONS

    class _BadCoder(CoderClient):
        name = "bad_stub"
        async def generate_tool(self, spec):
            return CodeGenResult(code=f"async def {spec.name}({', '.join(spec.parameters_schema or {})}): return None\n")
        async def revise_tool(self, prior, feedback):
            return prior  # Never improves.

    smith = Toolsmith(
        coder=_BadCoder(),
        artifact_store=ArtifactStore(tmp_path / "tools"),
        llm=False,
    )

    async def url_probe(realized, llm=None, timeout=None, auth=None, secrets=None):
        return {"ok": True, "status_code": 200, "response": {"data": [1]}, "reason": "url ok"}

    monkeypatch.setattr(probe_mod, "probe_realized_tool", url_probe)

    result = await smith.acquire({"capability": "country population currency"})
    assert not result.success
    assert "revision" in result.summary
    # Nothing persisted.
    assert smith.list_artifacts() == []
    # Find the revisions transcript step.
    revs_step = next(s for s in result.transcript if s["step"] == "exec_probe_revisions")
    assert len(revs_step["history"]) == _MAX_REVISIONS + 1  # initial + N revisions
