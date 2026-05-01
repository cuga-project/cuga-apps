"""Toolsmith's internal tool belt — what the LangGraph ReAct agent calls.

These are NOT MCP tools and not part of the user-facing tool catalog.
They are agent tools that Toolsmith uses to *build* the user-facing tools.

Each tool is a thin wrapper that closes over the service's state (the
Coder client, the catalog, the probe harness, the artifact store) and
returns plain JSON-serializable results — that's what LangGraph's tool
calling needs.

build_toolbelt() returns the list of LangChain tools given the runtime
deps; it's the single seam Toolsmith plugs into the ReAct loop.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx  # used by search_apis_guru_directory

log = logging.getLogger(__name__)

# Make backend/acquisition/* importable so we can reuse phase-2/3 logic
# without copying. This is read-only consumption.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent.parent  # cuga-apps/
_BACKEND = _REPO_ROOT / "chief_of_staff" / "backend"
for _p in (str(_BACKEND), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def build_toolbelt(coder, store, catalog, openapi_source, vault, mounted_callback,
                   browser_source=None):
    """Return the list of LangChain @tool callables for the ReAct agent.

    mounted_callback(artifact) is invoked after successful registration so
    the service can notify whoever cares (the backend, in our case).
    browser_source is the third-tier fallback (Playwright tasks) — when
    None, the browser-search/mount tools are simply omitted so older callers
    keep working.
    """
    from langchain_core.tools import tool  # type: ignore[import-not-found]

    from acquisition.probe import probe_realized_tool  # type: ignore[import-not-found]
    from acquisition.sources.base import RealizedTool  # type: ignore[import-not-found]

    from ..artifact import ToolArtifact, ToolManifest, make_id_from, now_iso
    from ..coders.base import CodeGenSpec

    # ── Search the curated catalog ───────────────────────────────────────
    @tool
    def search_catalog(capability: str) -> str:
        """Search the curated MCP-server catalog for tools matching a capability.

        Returns JSON: list of {id, name, description, score, kind, target}.
        Use this first when the gap looks like it could match an existing
        local MCP server (geo, knowledge, finance, text, invocable_apis).
        """
        proposals = catalog.match({"capability": capability})
        return json.dumps([
            {"id": p.entry.id, "name": p.entry.name, "description": p.entry.description,
             "score": round(p.score, 3), "kind": p.entry.kind, "target": p.entry.target}
            for p in proposals
        ])

    # ── Search the OpenAPI spec index ────────────────────────────────────
    @tool
    async def search_openapi_index(capability: str) -> str:
        """Search the curated OpenAPI spec index for APIs matching a capability.

        Returns JSON: list of {id, name, description, score, base_url, preview_endpoint}.
        Use this when no good catalog match exists and the gap likely needs
        an HTTP-API-shaped tool.
        """
        proposals = await openapi_source.propose({"capability": capability}, top_k=5)
        return json.dumps([
            {"id": p.id, "name": p.name, "description": p.description,
             "score": p.score, "base_url": p.spec.get("base_url"),
             "preview_endpoint": p.spec.get("preview_endpoint")}
            for p in proposals
        ])

    # ── Pull the full endpoint detail for a given OpenAPI spec id ───────
    @tool
    def describe_openapi_endpoint(spec_id: str) -> str:
        """Get full details (path, method, params, sample input) for the
        primary endpoint of an OpenAPI catalog entry. Use this after
        search_openapi_index picked a candidate — its output drives codegen."""
        entry = openapi_source.by_id(spec_id)
        if entry is None or not entry.endpoints:
            return json.dumps({"error": f"unknown spec_id: {spec_id}"})
        ep = entry.endpoints[0]
        return json.dumps({
            "spec_id": entry.id, "name": entry.name, "base_url": entry.base_url,
            "tool_name": ep.tool_name, "description": ep.description,
            "method": ep.method, "path": ep.path,
            "params": ep.params, "probe_input": ep.probe_input,
        })

    # ── Use the swappable Coder to generate Python source ───────────────
    @tool
    async def generate_tool_code(
        name: str, description: str, base_url: str, method: str, path: str,
        parameters_schema_json: str, sample_input_json: str,
    ) -> str:
        """Use the configured Coder (gpt-oss / Claude / etc.) to generate Python
        source for a new async tool that wraps an HTTP endpoint. Returns the
        generated code as a string. Caller probes it before registering."""
        try:
            params = json.loads(parameters_schema_json)
            sample = json.loads(sample_input_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"bad JSON arg: {exc}"})

        spec = CodeGenSpec(
            name=name, description=description,
            parameters_schema=params, sample_input=sample,
            api_base_url=base_url, api_method=method, api_path=path,
        )
        result = await coder.generate_tool(spec)
        return json.dumps({"code": result.code, "notes": result.notes, "coder": coder.name})

    # ── Probe a generated tool ──────────────────────────────────────────
    @tool
    async def probe_generated_tool(
        name: str, description: str, base_url: str, method: str, path: str,
        sample_input_json: str,
    ) -> str:
        """Run a probe call against an HTTP endpoint to verify it returns
        usable data. Returns JSON: {ok, reason, status_code, response (truncated)}.
        Always probe BEFORE register — never register an unverified tool."""
        try:
            sample = json.loads(sample_input_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"bad JSON arg: {exc}"})

        realized = RealizedTool(
            proposal_id=f"runtime:{name}", tool_name=name, description=description,
            invoke_url=f"{base_url.rstrip('/')}{path}",
            invoke_method=method, sample_input=sample,
        )
        result = await probe_realized_tool(realized)
        return json.dumps(result, default=str)

    # ── Register a successfully-probed tool as a persistent artifact ────
    @tool
    async def register_tool_artifact(
        name: str, description: str, code: str,
        parameters_schema_json: str, source: str,
        provenance_json: str = "{}",
        last_probe_json: str = "{}",
    ) -> str:
        """Persist the tool to disk as a ToolArtifact and notify the backend
        to mount it. Returns JSON {id, mounted}. Only call AFTER probe passes."""
        try:
            params = json.loads(parameters_schema_json)
            provenance = json.loads(provenance_json) or {}
            last_probe = json.loads(last_probe_json) or None
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"bad JSON arg: {exc}"})

        provenance.setdefault("created_at", now_iso())
        provenance.setdefault("coder", coder.name)
        provenance.setdefault("source", source)
        artifact_id = make_id_from(name, source=source)
        artifact = ToolArtifact(
            manifest=ToolManifest(
                id=artifact_id, name=name, description=description,
                parameters_schema=params, provenance=provenance,
            ),
            code=code, last_probe=last_probe,
        )
        store.save(artifact)
        # Tell the backend (or whoever subscribed) that we mounted something.
        await mounted_callback(artifact) if callable(mounted_callback) else None
        return json.dumps({"id": artifact_id, "mounted": True})

    # ── List artifacts already on disk ──────────────────────────────────
    @tool
    def list_existing_tools() -> str:
        """List tool artifacts that have already been built. Useful to avoid
        rebuilding a tool the user already has."""
        return json.dumps([a.to_summary() for a in store.list_all()])

    # ── Remove an artifact ──────────────────────────────────────────────
    @tool
    async def remove_tool_artifact(artifact_id: str) -> str:
        """Remove a previously-built tool artifact and tell the backend to
        unmount it. Returns JSON {removed: bool}."""
        ok = store.remove(artifact_id)
        if ok and callable(mounted_callback):
            # Re-trigger backend with current store state so it resyncs.
            await mounted_callback(None)
        return json.dumps({"removed": ok})

    # ── Vault accessors ─────────────────────────────────────────────────
    @tool
    def check_secret_available(tool_id: str, secret_key: str) -> str:
        """Check whether a given secret has been provided for a tool. Use
        before generating code that requires auth — if false, the tool
        cannot be probed yet and the caller needs to ask the user."""
        return json.dumps({"available": vault.get(tool_id, secret_key) is not None})

    @tool
    async def search_apis_guru_directory(query: str) -> str:
        """Phase 3.7: search the public APIs.guru directory for OpenAPI specs
        matching a free-text query. Use this only when the curated catalog
        and openapi index miss — APIs.guru indexes ~2,500 public APIs.

        Returns JSON: list of {name, description, spec_url, score} (top 5).
        Note: caller still needs to fetch and analyze the full spec before
        declaring an endpoint — this tool only narrows the search."""
        import re as _re
        query_tokens = set(_re.findall(r"[a-z0-9]+", (query or "").lower()))
        if not query_tokens:
            return json.dumps([])
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get("https://api.apis.guru/v2/list.json")
                r.raise_for_status()
                catalog = r.json()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"apis.guru unreachable: {exc}"})

        scored = []
        for provider, body in catalog.items():
            versions = (body or {}).get("versions") or {}
            preferred = (body or {}).get("preferred")
            v = versions.get(preferred) or (next(iter(versions.values())) if versions else {})
            info = (v.get("info") or {})
            text = " ".join([
                provider, info.get("title", ""), info.get("description", ""),
            ]).lower()
            tokens = set(_re.findall(r"[a-z0-9]+", text))
            overlap = query_tokens & tokens
            if not overlap:
                continue
            score = len(overlap) / max(len(query_tokens), 1)
            scored.append({
                "name": info.get("title") or provider,
                "description": (info.get("description") or "")[:200],
                "spec_url": v.get("swaggerUrl") or v.get("swaggerYamlUrl"),
                "score": round(score, 3),
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return json.dumps(scored[:5])

    # ── Browser-task tools (phase 4) ─────────────────────────────────────
    # Without these the ReAct agent has no way to discover or mount
    # curated browser tasks (school portals, bill-pay UIs, sites without
    # APIs). The deterministic fallback knows about them, but the ReAct
    # path has to be told explicitly.
    @tool
    async def search_browser_tasks(capability: str) -> str:
        """Search the curated browser-task templates for matches against a
        capability. Use this when no API source covers the gap — typical
        cases are sites without APIs (school portals, internal tools,
        scraped pages). Returns JSON: list of {id, name, description,
        score, requires_secrets, task_id}."""
        if browser_source is None:
            return json.dumps({"error": "browser source not configured"})
        proposals = await browser_source.propose({"capability": capability}, top_k=5)
        return json.dumps([
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "score": round(p.score, 3),
                "requires_secrets": list(p.auth or []),
                "task_id": p.spec.get("task_id"),
            }
            for p in proposals
        ])

    @tool
    async def mount_browser_task(task_id: str, capability: str) -> str:
        """Realize and register a curated browser task as a persistent
        artifact (kind=browser_task). The cuga adapter dispatches calls
        to the browser-runner service. If the task declares required
        secrets that aren't in the vault, returns {needs_secrets:[…]}
        instead of registering — the orchestrator surfaces that to the
        user."""
        if browser_source is None:
            return json.dumps({"error": "browser source not configured"})

        # Re-resolve the proposal so we have the full spec.
        proposals = await browser_source.propose({"capability": capability}, top_k=5)
        match = next((p for p in proposals if p.spec.get("task_id") == task_id), None)
        if match is None:
            return json.dumps({"error": f"unknown browser task_id: {task_id}"})

        realized = await browser_source.realize(match)
        prospective_id = make_id_from(realized.tool_name, source="browser")
        required = list(realized.requires_secrets or [])
        missing = vault.missing(prospective_id, required) if required else []
        if missing:
            return json.dumps({
                "needs_secrets": {
                    "tool_id": prospective_id,
                    "tool_name": realized.tool_name,
                    "missing": missing,
                    "required": required,
                },
                "registered": False,
            })

        task = browser_source.by_id(task_id)
        artifact = ToolArtifact(
            manifest=ToolManifest(
                id=prospective_id,
                name=realized.tool_name,
                description=realized.description,
                parameters_schema=realized.invoke_params,
                requires_secrets=required,
                provenance={
                    "source": "browser", "task_id": task_id,
                    "created_at": now_iso(),
                },
                kind="browser_task",
                steps=list(task.steps) if task else [],
            ),
            code="",
        )
        store.save(artifact)
        await mounted_callback(artifact)
        return json.dumps({
            "registered": True,
            "artifact_id": artifact.manifest.id,
            "tool_name": realized.tool_name,
        })

    base = [
        search_catalog,
        search_openapi_index,
        describe_openapi_endpoint,
        generate_tool_code,
        probe_generated_tool,
        register_tool_artifact,
        list_existing_tools,
        remove_tool_artifact,
        check_secret_available,
        search_apis_guru_directory,
    ]
    if browser_source is not None:
        base.extend([search_browser_tasks, mount_browser_task])
    return base
