"""HTTP client for the Toolsmith service.

Mirrors the cuga adapter pattern: the orchestrator never imports Toolsmith
internals; it talks to the service. That preserves Toolsmith as a
process-isolated, durable component the rest of the system doesn't depend
on except via this small contract.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)


@dataclass
class AcquireOutcome:
    success: bool
    artifact_id: Optional[str]
    summary: str
    transcript: list[dict]
    artifact: Optional[dict]   # mcp_tool_spec dict, or None on failure
    needs_secrets: Optional[dict] = None
    # Toolsmith decided the gap is already filled by an existing tool —
    # not a build failure. UI renders a different (informational) card.
    already_existed: bool = False


class ToolsmithClient:
    def __init__(self, url: str | None = None, timeout: float = 600.0):
        self._url = (url or os.environ.get("TOOLSMITH_URL", "http://localhost:8001")).rstrip("/")
        # Long timeout for /acquire — ReAct loops can take a while.
        self._client = httpx.AsyncClient(timeout=timeout)

    async def health(self) -> dict:
        try:
            r = await self._client.get(f"{self._url}/health", timeout=5.0)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            return {"status": "unreachable"}

    async def acquire(self, gap: dict) -> AcquireOutcome:
        try:
            r = await self._client.post(f"{self._url}/acquire", json={"gap": gap})
            r.raise_for_status()
            data = r.json()
            return AcquireOutcome(
                success=bool(data.get("success")),
                artifact_id=data.get("artifact_id"),
                summary=data.get("summary", ""),
                transcript=data.get("transcript", []),
                artifact=data.get("artifact"),
                needs_secrets=data.get("needs_secrets"),
                already_existed=bool(data.get("already_existed")),
            )
        except httpx.HTTPError as exc:
            log.warning("toolsmith /acquire failed: %s", exc)
            return AcquireOutcome(
                success=False, artifact_id=None,
                summary=f"toolsmith unreachable: {exc}",
                transcript=[], artifact=None, needs_secrets=None,
            )

    async def list_artifacts(self) -> list[dict]:
        try:
            r = await self._client.get(f"{self._url}/tools")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            return []

    async def all_artifact_specs(self) -> list[dict]:
        try:
            r = await self._client.get(f"{self._url}/specs/all_artifacts")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            log.warning("toolsmith /specs/all_artifacts failed: %s", exc)
            return []

    async def effective_state(self) -> dict:
        """Returns {mcp_servers: list[str], extra_tools: list[dict]} —
        the merged state the backend hands to cuga's /agent/reload."""
        try:
            r = await self._client.get(f"{self._url}/effective_state")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            log.warning("toolsmith /effective_state failed: %s", exc)
            return {"mcp_servers": [], "extra_tools": []}

    async def remove_artifact(self, artifact_id: str) -> bool:
        try:
            r = await self._client.delete(f"{self._url}/tools/{artifact_id}")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    # ── Vault proxies ────────────────────────────────────────────────────
    async def vault_put(self, tool_id: str, secret_key: str, value: str) -> dict:
        r = await self._client.post(
            f"{self._url}/vault/secret",
            json={"tool_id": tool_id, "secret_key": secret_key, "value": value},
        )
        r.raise_for_status()
        return r.json()

    async def vault_delete(self, tool_id: str, secret_key: str | None = None) -> dict:
        r = await self._client.post(
            f"{self._url}/vault/delete",
            json={"tool_id": tool_id, "secret_key": secret_key},
        )
        r.raise_for_status()
        return r.json()

    async def vault_list_keys(self, tool_id: str) -> dict:
        r = await self._client.get(f"{self._url}/vault/keys/{tool_id}")
        r.raise_for_status()
        return r.json()

    async def vault_missing(self, artifact_id: str) -> dict:
        r = await self._client.get(f"{self._url}/vault/missing/{artifact_id}")
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()
