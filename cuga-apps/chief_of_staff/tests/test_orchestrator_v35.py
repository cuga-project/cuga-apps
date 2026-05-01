"""Orchestrator tests for the phase-3.5 architecture.

Backend orchestrator now coordinates two services (cuga adapter + toolsmith)
both via HTTP. We stub both at the client level.
"""

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from agents.base import AgentClient, AgentResult, ToolGap  # noqa: E402
from agents.toolsmith_client import AcquireOutcome  # noqa: E402
from orchestrator import Orchestrator  # noqa: E402


class _StubPlanner(AgentClient):
    def __init__(self):
        self.reload_calls: list[tuple[list[str], list[dict], dict]] = []
        self.next_result: AgentResult = AgentResult(answer="ok")

    async def plan_and_execute(self, message, thread_id="default"):
        return self.next_result

    async def reload(self, servers, extra_tools=None, secrets=None, disabled_tools=None):
        self.reload_calls.append((list(servers), list(extra_tools or []), dict(secrets or {})))
        return {"status": "ok", "servers_loaded": list(servers),
                "tool_count": len(servers) * 5 + len(extra_tools or []),
                "extra_tool_count": len(extra_tools or [])}

    async def health(self): return True
    async def aclose(self): pass


class _StubToolsmithClient:
    def __init__(self):
        self.acquire_calls: list[dict] = []
        self.next_outcome = AcquireOutcome(
            success=False, artifact_id=None, summary="", transcript=[], artifact=None,
        )
        self.next_state = {"mcp_servers": [], "extra_tools": []}

    async def acquire(self, gap):
        self.acquire_calls.append(gap)
        return self.next_outcome

    async def health(self): return {"status": "ok", "coder": "stub", "orchestration_llm": False, "artifact_count": 0}
    async def list_artifacts(self): return []
    async def all_artifact_specs(self): return []
    async def effective_state(self): return self.next_state
    async def remove_artifact(self, _id): return True
    async def aclose(self): pass


@pytest.fixture
def orch(monkeypatch):
    monkeypatch.setenv("MCP_SERVERS", "web,local,code")
    p = _StubPlanner()
    t = _StubToolsmithClient()
    return Orchestrator(planner=p, toolsmith=t), p, t


@pytest.mark.asyncio
async def test_chat_no_gap_skips_toolsmith(orch):
    o, planner, toolsmith = orch
    planner.next_result = AgentResult(answer="hello")
    turn = await o.chat("hi")
    assert turn.acquisition is None
    assert toolsmith.acquire_calls == []


@pytest.mark.asyncio
async def test_chat_with_gap_calls_toolsmith(orch):
    o, planner, toolsmith = orch
    planner.next_result = AgentResult(
        answer="I need a tool.",
        gap=ToolGap(capability="weather lookup"),
    )
    toolsmith.next_outcome = AcquireOutcome(
        success=True, artifact_id="openapi__get_weather", summary="Built it.",
        transcript=[], artifact={"tool_name": "get_weather"},
    )
    toolsmith.next_state = {"mcp_servers": [], "extra_tools": [{"tool_name": "get_weather"}]}

    turn = await o.chat("what's the weather")
    assert turn.acquisition is not None
    assert turn.acquisition["success"] is True
    assert turn.acquisition["artifact_id"] == "openapi__get_weather"

    # After successful acquire, planner should be reloaded with the new state.
    servers, extras, _secrets = planner.reload_calls[-1]
    assert "web" in servers and "local" in servers and "code" in servers
    assert extras == [{"tool_name": "get_weather"}]


@pytest.mark.asyncio
async def test_chat_with_gap_failure_does_not_reload(orch):
    o, planner, toolsmith = orch
    planner.next_result = AgentResult(
        answer="I need a tool.",
        gap=ToolGap(capability="DoorDash food delivery"),
    )
    toolsmith.next_outcome = AcquireOutcome(
        success=False, artifact_id=None, summary="No match.",
        transcript=[], artifact=None,
    )
    n_before = len(planner.reload_calls)
    turn = await o.chat("doordash")
    assert turn.acquisition["success"] is False
    assert len(planner.reload_calls) == n_before


@pytest.mark.asyncio
async def test_sync_planner_merges_baseline_and_state(orch):
    o, planner, toolsmith = orch
    toolsmith.next_state = {
        "mcp_servers": ["geo", "knowledge"],
        "extra_tools": [{"tool_name": "get_country_by_name"}],
    }
    await o.sync_planner_with_toolsmith()
    servers, extras, _secrets = planner.reload_calls[-1]
    assert servers == ["web", "local", "code", "geo", "knowledge"]
    assert extras == [{"tool_name": "get_country_by_name"}]


@pytest.mark.asyncio
async def test_remove_artifact_triggers_resync(orch):
    o, planner, _toolsmith = orch
    n_before = len(planner.reload_calls)
    ok = await o.remove_artifact("some-id")
    assert ok
    assert len(planner.reload_calls) == n_before + 1
