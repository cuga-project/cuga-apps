"""Orchestrator — the seam between the chat surface and the two services.

Phase 3.5:
- Toolsmith is now a separate FastAPI service, not in-process.
- On a gap, the orchestrator POSTs to Toolsmith /acquire and lets the
  ReAct agent do its thing autonomously. The result is shown in the chat.
- After acquisition (or on backend startup, or on artifacts_changed
  webhook from Toolsmith), we pull /effective_state and reload cuga.
- Catalog mounts are now ToolArtifacts too — the activations table from
  phase 2 is no longer authoritative.

Cuga adapter remains the only swappable planner.
Toolsmith service is the durable acquisition agent.
The orchestrator is the thin coordinator between them.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass

from agents.base import AgentClient
from agents.cuga_client import CugaClient
from agents.toolsmith_client import AcquireOutcome, ToolsmithClient

log = logging.getLogger(__name__)


@dataclass
class ChatTurn:
    answer: str
    error: str | None
    gap: dict | None
    acquisition: dict | None   # {success, artifact_id, summary, transcript} or None
    tools_used: list[dict] | None = None  # [{name, server}, …]


def _build_planner() -> AgentClient:
    name = os.environ.get("CHIEF_OF_STAFF_AGENT", "cuga").lower()
    if name == "cuga":
        return CugaClient()
    raise ValueError(f"Unknown planner backend: {name!r}")


def _baseline_servers() -> list[str]:
    raw = os.environ.get("MCP_SERVERS", "web,local,code")
    return [s.strip() for s in raw.split(",") if s.strip()]


class Orchestrator:
    def __init__(
        self,
        planner: AgentClient | None = None,
        toolsmith: ToolsmithClient | None = None,
    ):
        self._planner = planner or _build_planner()
        self._toolsmith = toolsmith or ToolsmithClient()
        # Tool names the user has disabled via the UI. In-memory only —
        # acceptable since disabling is meant to be a transient, demo-time
        # gesture ("disable web_search and try the same question again").
        self._disabled_tools: set[str] = set()

    @property
    def planner(self) -> AgentClient:
        return self._planner

    @property
    def toolsmith(self) -> ToolsmithClient:
        return self._toolsmith

    @property
    def disabled_tools(self) -> set[str]:
        return set(self._disabled_tools)

    @property
    def baseline_servers(self) -> set[str]:
        """MCP server names from the env (baseline cold-start set). Tools
        whose server isn't here got mounted by Toolsmith — surfaced in the
        UI under 'Acquired by Toolsmith'."""
        return set(_baseline_servers())

    async def set_tool_disabled(self, name: str, disabled: bool) -> set[str]:
        if disabled:
            self._disabled_tools.add(name)
        else:
            self._disabled_tools.discard(name)
        try:
            await self.sync_planner_with_toolsmith()
        except Exception:  # noqa: BLE001
            log.exception("planner reload after disable-toggle failed")
        return self.disabled_tools

    async def chat(self, message: str, thread_id: str = "default") -> ChatTurn:
        # Force a fresh per-message thread on the planner to keep cuga's
        # internal chat history bounded — accumulating it across turns
        # bloats the prompt past gpt-oss-120b's context, which the model
        # reacts to by truncating output mid-generation. Conversational
        # context is rendered client-side from the local message list, so
        # cuga's cross-turn memory isn't load-bearing here.
        planner_thread = f"{thread_id}-{uuid.uuid4().hex[:8]}"
        result = await self._planner.plan_and_execute(message, thread_id=planner_thread)
        acquisition = None

        if result.gap is not None:
            gap = result.gap.to_json()
            outcome = await self._toolsmith.acquire(gap)
            acquisition = {
                "success": outcome.success,
                "artifact_id": outcome.artifact_id,
                "summary": outcome.summary,
                "transcript": outcome.transcript,
                "needs_secrets": outcome.needs_secrets,
                "already_existed": outcome.already_existed,
            }
            should_retry = False
            if outcome.success:
                # Toolsmith built and registered a new tool. Sync the
                # planner so cuga's adapter sees it, then re-ask the user's
                # original question against a fresh thread — the cuga
                # response on the original turn was empty (cuga had just
                # emitted the gap marker), so without retry the user sees
                # only the green "tool built" card and no answer.
                try:
                    await self.sync_planner_with_toolsmith()
                    should_retry = True
                except Exception:  # noqa: BLE001
                    log.exception("planner reload after acquire failed")
            elif outcome.already_existed:
                # Toolsmith decided the toolbox already covers the gap, but
                # cuga emitted a gap anyway — usually because the relevant
                # tool wasn't visible to cuga in this turn (e.g. an extra
                # silently failed to build, or cuga's selection didn't
                # latch). Re-running the same prompt against a fresh thread
                # lets cuga try again with the full toolset.
                log.info("acquisition already_existed; retrying original message")
                try:
                    await self.sync_planner_with_toolsmith()
                except Exception:  # noqa: BLE001
                    log.exception("planner sync before retry failed")
                should_retry = True

            if should_retry:
                retry_thread = f"{thread_id}-retry-{uuid.uuid4().hex[:8]}"
                retry_result = await self._planner.plan_and_execute(
                    message, thread_id=retry_thread,
                )
                # Use the retry's answer/error/tools_used; keep the
                # acquisition card so the user understands what happened.
                result = retry_result

        return ChatTurn(
            answer=result.answer,
            error=result.error,
            gap=result.gap.to_json() if result.gap is not None else None,
            acquisition=acquisition,
            tools_used=list(result.tools_used or []),
        )

    async def sync_planner_with_toolsmith(self) -> dict:
        """Pull effective state from Toolsmith and reload the planner.

        Called: (a) on backend startup, (b) after each successful acquisition,
        (c) on the /internal/artifacts_changed webhook (also fires when a
            secret is added/removed — a previously-blocked tool may unblock).
        """
        state = await self._toolsmith.effective_state()
        servers = list(_baseline_servers())
        for s in state.get("mcp_servers", []):
            if s not in servers:
                servers.append(s)
        extra_tools = state.get("extra_tools", [])
        secrets = state.get("secrets", {}) or {}
        return await self._planner.reload(
            servers,
            extra_tools=extra_tools,
            secrets=secrets,
            disabled_tools=sorted(self._disabled_tools),
        )

    async def remove_artifact(self, artifact_id: str) -> bool:
        ok = await self._toolsmith.remove_artifact(artifact_id)
        if ok:
            try:
                await self.sync_planner_with_toolsmith()
            except Exception:  # noqa: BLE001
                log.exception("reload after remove failed")
        return ok

    async def planner_health(self) -> bool:
        return await self._planner.health()

    async def planner_failed_extras(self) -> list[dict]:
        """Adapter's silent extra-tool build failures (artifacts that
        Toolsmith registered but the adapter couldn't load — typically
        schema mismatches or import-allowlist hits). Surfaced via /health
        so the UI can flag them."""
        url = os.environ.get("CUGA_URL", "http://localhost:8000").rstrip("/")
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{url}/health")
                r.raise_for_status()
                return list((r.json() or {}).get("failed_extras") or [])
        except httpx.HTTPError:
            return []

    async def toolsmith_health(self) -> dict:
        return await self._toolsmith.health()

    async def list_toolsmith_artifacts(self) -> list[dict]:
        return await self._toolsmith.list_artifacts()

    async def aclose(self) -> None:
        await self._planner.aclose()
        await self._toolsmith.aclose()
