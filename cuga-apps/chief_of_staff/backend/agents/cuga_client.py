"""Cuga AgentClient — out-of-process HTTP client.

If no cuga is reachable at CUGA_URL, falls back to echoing so the chat loop
stays testable while you debug. Real planning happens once the adapter is up.
"""

from __future__ import annotations

import os

import httpx

from .base import AgentClient, AgentResult, ToolGap


class CugaClient(AgentClient):
    def __init__(self, url: str | None = None, timeout: float = 60.0):
        self._url = (url or os.environ.get("CUGA_URL", "http://localhost:8000")).rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def plan_and_execute(self, user_message: str, thread_id: str = "default") -> AgentResult:
        try:
            r = await self._client.post(
                f"{self._url}/chat",
                json={"message": user_message, "thread_id": thread_id},
            )
            r.raise_for_status()
            data = r.json()
            gap = ToolGap.from_json(data["gap"]) if data.get("gap") else None
            return AgentResult(
                answer=data.get("response", ""),
                error=data.get("error"),
                gap=gap,
                tools_used=list(data.get("tools_used") or []),
            )
        except (httpx.HTTPError, ValueError):
            return AgentResult(
                answer=f"[stub:cuga-unreachable] echo: {user_message}",
            )

    async def reload(
        self,
        servers: list[str],
        extra_tools: list[dict] | None = None,
        secrets: dict[str, dict[str, str]] | None = None,
        disabled_tools: list[str] | None = None,
    ) -> dict:
        # 5-minute timeout — rebuilding the agent + handshaking with all MCP
        # servers takes ~30s in practice but can spike on cold start.
        r = await self._client.post(
            f"{self._url}/agent/reload",
            json={
                "servers": servers,
                "extra_tools": list(extra_tools or []),
                "secrets": dict(secrets or {}),
                "disabled_tools": list(disabled_tools or []),
            },
            timeout=300.0,
        )
        r.raise_for_status()
        return r.json()

    async def health(self) -> bool:
        try:
            r = await self._client.get(f"{self._url}/health")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
