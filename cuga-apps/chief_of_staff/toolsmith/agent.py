"""LangGraph ReAct Toolsmith — the durable acquisition agent.

This is the brain. It owns the *whole* loop: gap → propose → generate →
probe → register. Cuga (the planner) is swappable; Toolsmith stays.

The agent itself uses an LLM (gpt-oss-120b by default) for reasoning,
and a separate **Coder** (also configurable) when it concludes "I need
code now." See coders/base.py for the Coder protocol.

Falls back to a deterministic path (catalog → openapi → realize → probe →
register) when no LLM is configured, so the loop still runs end-to-end
without RITS / Anthropic credentials — useful for tests.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .artifact import ArtifactStore, ToolArtifact, ToolManifest, make_id_from, now_iso
from .coders.base import CoderClient, CodeGenSpec, CodeGenResult, ProbeFailure, coder_from_env
from .tools.build import build_toolbelt

# Phase 3.8 — bound the revise loop. 3 retries is plenty in practice;
# beyond that the Coder is usually working from a flawed premise.
_MAX_REVISIONS = 3

log = logging.getLogger(__name__)

# Make backend/acquisition reachable for sources/probe/vault.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent
_BACKEND = _REPO_ROOT / "chief_of_staff" / "backend"
for _p in (str(_BACKEND), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


_TOOLSMITH_SYSTEM_PROMPT = """\
You are Toolsmith, an agent that builds tools to fill capability gaps.

When given a gap, work through these tiers in order until one succeeds:

  Tier 1 — Existing toolbox & curated catalog (fastest, most reliable)
    - Check what's already installed (list_existing_tools).
    - Search the curated catalog (search_catalog).

  Tier 2 — Public APIs (general coverage, OpenAPI-driven)
    - Search the curated OpenAPI index (search_openapi_index) and the
      broader APIs.guru directory (search_apis_guru_directory).
    - Pick the best candidate, gather endpoint detail
      (describe_openapi_endpoint), generate code (generate_tool_code),
      probe (probe_generated_tool), then register (register_tool_artifact).

  Tier 3 — Curated browser tasks (last resort, for sites without APIs)
    - When a gap clearly involves a website that does NOT expose an API
      — school portals, utility billing UIs, school grade systems,
      employee self-service portals, anything where "log into the site
      and read the page" is the only path — use search_browser_tasks
      to look for a curated template, then mount_browser_task to
      register it. If the template requires secrets that aren't set,
      mount_browser_task returns needs_secrets — STOP there; do not
      retry. The orchestrator will ask the user for credentials.

Strong signal that you should jump straight to Tier 3:
  - The gap mentions "portal", "login required", "behind a login",
    "school", "internal site", "bill", "dashboard", or names a site
    with no public API.

Always probe BEFORE registering APIs. Never register an unverified tool.
Browser tasks may be registered without remote probing — the runner
validates the steps at execution time.

Be terse — your reasoning becomes the audit trail. When done, end with a
final message describing what you built (or why you couldn't).
"""


@dataclass
class AcquireResult:
    success: bool
    artifact_id: Optional[str]
    summary: str
    transcript: list[dict]
    # Phase 3.6: when an acquisition is blocked because the user hasn't
    # provided required credentials, this carries the details so the UI can
    # prompt for them. Distinct from regular failure (probe miss, etc.).
    needs_secrets: Optional[dict] = None  # {tool_id, required, missing, help}
    # The ReAct agent looked at the existing toolbox via list_existing_tools
    # and decided the gap is already covered. From the user's perspective
    # this is a success — the answer should flow on retry, not "couldn't
    # build a tool." UI uses this flag to render a different card.
    already_existed: bool = False


class Toolsmith:
    def __init__(
        self,
        coder: Optional[CoderClient] = None,
        artifact_store: Optional[ArtifactStore] = None,
        on_artifact_change: Optional[Callable[[Optional[ToolArtifact]], Awaitable[None]]] = None,
        llm=None,
    ):
        self._coder = coder or coder_from_env()
        self._store = artifact_store or ArtifactStore()
        self._on_change = on_artifact_change or _noop_async
        if llm is False:
            self._llm = None
        elif llm is None:
            self._llm = _try_build_orchestration_llm()
        else:
            self._llm = llm

        from acquisition.catalog import Catalog  # type: ignore[import-not-found]
        from acquisition.sources.openapi_source import OpenAPISource  # type: ignore[import-not-found]
        from acquisition.sources.browser_source import BrowserSource  # type: ignore[import-not-found]
        from acquisition.vault import Vault  # type: ignore[import-not-found]
        self._catalog = Catalog()
        self._openapi_source = OpenAPISource()
        self._browser_source = BrowserSource()
        self._vault = Vault()

        # Build the agent's tool belt once. Browser source is wired in so
        # the ReAct loop has access to search_browser_tasks / mount_browser_task.
        self._toolbelt = build_toolbelt(
            coder=self._coder, store=self._store, catalog=self._catalog,
            openapi_source=self._openapi_source, vault=self._vault,
            mounted_callback=self._on_change,
            browser_source=self._browser_source,
        )

    @property
    def coder(self) -> CoderClient:
        return self._coder

    @property
    def store(self) -> ArtifactStore:
        return self._store

    @property
    def vault(self):
        return self._vault

    @property
    def llm(self):
        return self._llm

    def list_artifacts(self) -> list[dict]:
        return [a.to_summary() for a in self._store.list_all()]

    async def remove_artifact(self, artifact_id: str) -> bool:
        ok = self._store.remove(artifact_id)
        if ok:
            await self._on_change(None)
        return ok

    async def _acquire_browser(self, proposal) -> "AcquireResult":
        """Phase 4 — realize a curated browser task, check secret availability,
        optionally probe via the browser-runner, and register."""
        import os
        from .artifact import make_id_from
        realized = await self._browser_source.realize(proposal)
        prospective_id = make_id_from(realized.tool_name, source="browser")

        if realized.requires_secrets:
            missing = self._vault.missing(prospective_id, realized.requires_secrets)
            if missing:
                return AcquireResult(
                    success=False, artifact_id=None,
                    summary=(
                        f"Browser task {proposal.name} needs credentials before "
                        f"I can install it: " + ", ".join(missing) + "."
                    ),
                    transcript=[{"step": "browser_auth_block", "missing": missing}],
                    needs_secrets={
                        "tool_id": prospective_id,
                        "tool_name": realized.tool_name,
                        "api_name": proposal.name,
                        "required": list(realized.requires_secrets),
                        "missing": missing,
                        "auth": {"type": "browser_session"},
                        "help": (
                            "Browser tasks need login credentials. They're "
                            "stored locally in the vault and only sent to the "
                            "browser-runner; never logged."
                        ),
                    },
                )

        # Probe via browser-runner. If unreachable, fall through and register
        # without probing — the user can wire the runner later. Logged but
        # non-fatal so the deterministic-mode tests still work.
        runner_url = os.environ.get(
            "BROWSER_RUNNER_URL", "http://chief-of-staff-browser:8002"
        ).rstrip("/")
        task = self._browser_source.by_id(proposal.spec["task_id"])
        steps = task.steps if task else []
        secrets_for_probe = self._vault.all_secrets_for(prospective_id) if realized.requires_secrets else {}

        probe_result: dict = {"ok": True, "reason": "probe skipped (runner unreachable)"}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{runner_url}/probe", json={
                    "steps": steps,
                    "sample_input": realized.sample_input,
                    "secrets": secrets_for_probe,
                })
                r.raise_for_status()
                probe_result = r.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("Browser-runner probe failed/skipped: %s", exc)

        if not probe_result.get("ok"):
            return AcquireResult(
                success=False, artifact_id=None,
                summary=f"Browser probe failed: {probe_result.get('reason', 'unknown')}",
                transcript=[{"step": "browser_probe", "result": probe_result}],
            )

        from toolsmith.artifact import ToolArtifact, ToolManifest
        artifact = ToolArtifact(
            manifest=ToolManifest(
                id=prospective_id,
                name=realized.tool_name,
                description=realized.description or "",
                parameters_schema=realized.invoke_params,
                requires_secrets=list(realized.requires_secrets),
                provenance={
                    "source": "browser", "task_id": proposal.spec.get("task_id"),
                    "created_at": now_iso(),
                },
                kind="browser_task",
                steps=steps,
            ),
            code="",  # browser tasks have no Python body
            last_probe={**probe_result, "at": now_iso()},
        )
        self._store.save(artifact)
        await self._on_change(artifact)
        return AcquireResult(
            success=True, artifact_id=artifact.manifest.id,
            summary=f"Mounted browser task {proposal.name}.",
            transcript=[
                {"step": "browser_probe", "result": probe_result},
                {"step": "register", "artifact_id": artifact.manifest.id},
            ],
        )

    async def acquire(self, gap: dict) -> AcquireResult:
        """Take a gap, do the loop, return the outcome.

        With an LLM configured: ReAct loop using the tool belt.
        Without: deterministic path that still proves the architecture.
        """
        if self._llm is None:
            return await self._deterministic_acquire(gap)
        try:
            return await self._react_acquire(gap)
        except Exception as exc:  # noqa: BLE001
            log.exception("ReAct acquire failed; falling back to deterministic path")
            det = await self._deterministic_acquire(gap)
            det.summary += f" (ReAct attempt errored: {exc})"
            return det

    # ------------------------------------------------------------------
    # ReAct path (LLM-driven)
    # ------------------------------------------------------------------
    async def _react_acquire(self, gap: dict) -> AcquireResult:
        from langgraph.prebuilt import create_react_agent  # type: ignore[import-not-found]

        agent = create_react_agent(model=self._llm, tools=self._toolbelt, prompt=_TOOLSMITH_SYSTEM_PROMPT)
        user = (
            "A planner agent reported this gap and needs a tool:\n"
            f"{json.dumps(gap, indent=2)}\n\n"
            "Build a tool that fills it. Probe before registering. "
            "When done, output a one-sentence summary."
        )
        result = await agent.ainvoke({"messages": [("user", user)]})
        transcript = _extract_transcript(result)
        artifact_id = _last_registered_id(transcript)
        if artifact_id is None:
            # The ReAct path may have hit a needs_secrets response from
            # mount_browser_task (or any tool that surfaces blocked-on-creds).
            # Surface it cleanly so the UI can prompt for credentials —
            # without this, the user sees a generic "couldn't build a tool"
            # and there's no way to unblock.
            needs = _last_needs_secrets(transcript)
            summary = _final_message(result) or "Toolsmith did not register a tool."

            # The agent may have looked at list_existing_tools and decided
            # the gap is already covered. That's not a failure — the
            # toolbox already does what was asked; the user just needs to
            # retry the original prompt. Flag it so the UI can render a
            # different card (and the orchestrator can auto-retry).
            already = needs is None and _looks_like_already_existed(transcript, summary)
            return AcquireResult(
                success=False, artifact_id=None,
                summary=summary,
                transcript=transcript,
                needs_secrets=needs,
                already_existed=already,
            )
        return AcquireResult(success=True, artifact_id=artifact_id,
                             summary=_final_message(result),
                             transcript=transcript)

    # ------------------------------------------------------------------
    # Deterministic path (no LLM)
    # ------------------------------------------------------------------
    async def _deterministic_acquire(self, gap: dict) -> AcquireResult:
        """Best-effort fallback when no LLM is configured. Compares the
        best catalog match vs best OpenAPI match by score and picks the winner.
        """
        from acquisition.probe import probe_realized_tool  # type: ignore[import-not-found]

        cat_proposals = self._catalog.match(gap, top_k=1)
        op_proposals = await self._openapi_source.propose(gap, top_k=1)
        br_proposals = await self._browser_source.propose(gap, top_k=1)

        cat_score = cat_proposals[0].score if cat_proposals else 0.0
        op_score = op_proposals[0].score if op_proposals else 0.0
        br_score = br_proposals[0].score if br_proposals else 0.0

        # API sources outrank browser when scores tie (cheaper, more reliable).
        # Browser only wins when no API source is plausible.
        prefer_catalog = cat_score >= op_score and cat_score >= br_score and cat_score >= 0.2
        prefer_openapi = op_score >= br_score and op_score >= 0.2 and not prefer_catalog
        prefer_browser = br_score >= 0.2 and not prefer_catalog and not prefer_openapi

        # Catalog first.
        if prefer_catalog:
            entry = cat_proposals[0].entry
            artifact = ToolArtifact(
                manifest=ToolManifest(
                    id=make_id_from(entry.id, source="catalog"),
                    name=entry.target, description=entry.description,
                    parameters_schema={},
                    provenance={"source": "catalog", "catalog_id": entry.id, "created_at": now_iso()},
                ),
                code=f"# Catalog mount of MCP server {entry.target!r} — no Python body, "
                     f"loaded by the cuga adapter via load_tools([\"{entry.target}\"])\n",
            )
            self._store.save(artifact)
            await self._on_change(artifact)
            return AcquireResult(
                success=True, artifact_id=artifact.manifest.id,
                summary=f"Mounted catalog server {entry.name} (deterministic path).",
                transcript=[{"step": "catalog_match", "entry_id": entry.id}],
            )

        # Browser fallback (phase 4) — only when API sources don't fit.
        if prefer_browser and br_proposals:
            return await self._acquire_browser(br_proposals[0])

        # OpenAPI fallback.
        if not op_proposals:
            return AcquireResult(
                success=False, artifact_id=None,
                summary="No catalog, OpenAPI, or browser-task match for this gap.",
                transcript=[],
            )
        proposal = op_proposals[0]
        realized = await self._openapi_source.realize(proposal)

        # Auth check — if the chosen API needs secrets we don't have, stop
        # before probing and tell the caller what's missing.
        auth_meta = (proposal.spec or {}).get("auth")
        prospective_id = make_id_from(realized.tool_name, source="openapi")
        if realized.requires_secrets:
            missing = self._vault.missing(prospective_id, realized.requires_secrets)
            if missing:
                return AcquireResult(
                    success=False, artifact_id=None,
                    summary=(
                        f"{proposal.name} needs credentials before I can build it: "
                        + ", ".join(missing) + "."
                    ),
                    transcript=[{"step": "auth_block", "missing": missing}],
                    needs_secrets={
                        "tool_id": prospective_id,
                        "tool_name": realized.tool_name,
                        "api_name": proposal.name,
                        "required": list(realized.requires_secrets),
                        "missing": missing,
                        "auth": auth_meta,
                        "help": (auth_meta or {}).get("help", ""),
                    },
                )

        # Run the probe with secrets injected if any.
        probe_secrets = (
            self._vault.all_secrets_for(prospective_id) if realized.requires_secrets else {}
        )
        probe = await probe_realized_tool(realized, auth=auth_meta, secrets=probe_secrets)

        # Phase 3.8 — if the *first* probe fails for reasons other than auth,
        # we'll attempt the code-revise loop AFTER we have a candidate code
        # body. The loop lives in the codegen block below.
        if not probe.get("ok"):
            return AcquireResult(
                success=False, artifact_id=None,
                summary=f"OpenAPI candidate failed probe: {probe.get('reason')}",
                transcript=[{"step": "openapi_probe", "result": probe}],
            )
        # Generate code via the Coder if available, else fall back to a
        # parameter-binding stub the adapter can execute.
        codegen_spec = CodeGenSpec(
            name=realized.tool_name, description=realized.description or "",
            parameters_schema=realized.invoke_params,
            sample_input=realized.sample_input,
            api_base_url=proposal.spec.get("base_url"),
            api_method=realized.invoke_method,
            api_path=realized.invoke_url.replace(proposal.spec.get("base_url", ""), "")
                if proposal.spec.get("base_url") else realized.invoke_url,
            requires_secrets=realized.requires_secrets,
            auth=auth_meta,
        )
        revisions: list[dict] = []
        try:
            code_result = await self._coder.generate_tool(codegen_spec)
            coder_name = self._coder.name
        except Exception as exc:  # noqa: BLE001
            log.warning("Coder unavailable in deterministic path: %s", exc)
            code_result = CodeGenResult(code=_fallback_stub_code(realized, auth_meta), notes="fallback")
            coder_name = "fallback_stub"

        # Phase 3.8 — revise loop. Execute the generated code; if it fails,
        # ask the Coder to revise based on the failure. Up to _MAX_REVISIONS.
        from acquisition.probe import probe_executed_code  # type: ignore[import-not-found]
        exec_probe: dict = {}
        for attempt in range(_MAX_REVISIONS + 1):
            exec_probe = await probe_executed_code(
                code_result.code, realized.tool_name,
                realized.sample_input, secrets=probe_secrets,
            )
            revisions.append({
                "attempt": attempt, "ok": exec_probe.get("ok"),
                "reason": exec_probe.get("reason"),
            })
            if exec_probe.get("ok") or coder_name == "fallback_stub":
                break
            if attempt == _MAX_REVISIONS:
                break
            try:
                feedback = ProbeFailure(
                    reason=exec_probe.get("reason", ""),
                    status_code=exec_probe.get("status_code"),
                    response_excerpt=str(exec_probe.get("response_excerpt", ""))[:600],
                )
                code_result = await self._coder.revise_tool(code_result, feedback)
            except Exception as exc:  # noqa: BLE001
                log.warning("Coder.revise_tool failed: %s — keeping last code", exc)
                break

        code = code_result.code
        if not exec_probe.get("ok"):
            return AcquireResult(
                success=False, artifact_id=None,
                summary=(
                    f"Generated code failed exec-probe after {len(revisions) - 1} "
                    f"revision(s): {exec_probe.get('reason', 'unknown')}"
                ),
                transcript=[
                    {"step": "url_probe", "result": probe},
                    {"step": "exec_probe_revisions", "history": revisions},
                ],
            )

        artifact = ToolArtifact(
            manifest=ToolManifest(
                id=prospective_id,
                name=realized.tool_name, description=realized.description or "",
                parameters_schema=realized.invoke_params,
                requires_secrets=list(realized.requires_secrets),
                provenance={
                    "source": "openapi", "spec_id": proposal.spec.get("spec_id"),
                    "coder": coder_name, "created_at": now_iso(),
                    "auth_type": (auth_meta or {}).get("type"),
                    "revisions": revisions,
                },
                auth=auth_meta,
            ),
            code=code,
            last_probe={**probe, "exec_probe": exec_probe, "at": now_iso()},
        )
        self._store.save(artifact)
        await self._on_change(artifact)
        revision_summary = (
            f" after {len(revisions) - 1} revision(s)" if len(revisions) > 1 else ""
        )
        return AcquireResult(
            success=True, artifact_id=artifact.manifest.id,
            summary=(
                f"Generated {realized.tool_name} via {coder_name}{revision_summary} "
                f"and probed successfully."
            ),
            transcript=[
                {"step": "url_probe", "result": probe},
                {"step": "exec_probe_revisions", "history": revisions},
                {"step": "register", "artifact_id": artifact.manifest.id},
            ],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _noop_async(*_a, **_kw):
    return None


# ---------------------------------------------------------------------------
# Phase 4 — browser acquisition
# ---------------------------------------------------------------------------


def _try_build_orchestration_llm():
    """The LLM Toolsmith uses for ReAct reasoning. Different from the Coder
    LLM — this one's job is routing/decisions, not code generation."""
    provider = os.environ.get("TOOLSMITH_LLM_PROVIDER", "rits")
    model = os.environ.get("TOOLSMITH_LLM_MODEL", "gpt-oss-120b")
    try:
        from _llm import create_llm  # type: ignore[import-not-found]
        return create_llm(provider=provider, model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("Toolsmith orchestration LLM unavailable: %s", exc)
        return None


def _extract_transcript(react_result: Any) -> list[dict]:
    """Pull a flat list of {role, content} from LangGraph's message history."""
    out = []
    for m in react_result.get("messages", []) if isinstance(react_result, dict) else []:
        out.append({
            "role": getattr(m, "type", None) or "unknown",
            "content": str(getattr(m, "content", "")),
        })
    return out


def _last_registered_id(transcript: list[dict]) -> Optional[str]:
    """Walk the transcript backwards looking for register_tool_artifact's
    JSON output. Returns the artifact id if found."""
    for entry in reversed(transcript):
        content = entry.get("content", "")
        if "\"id\"" in content and "\"mounted\"" in content:
            try:
                obj = json.loads(content)
                if obj.get("mounted"):
                    return obj.get("id")
            except json.JSONDecodeError:
                continue
    return None


def _final_message(react_result: Any) -> str:
    msgs = react_result.get("messages", []) if isinstance(react_result, dict) else []
    if not msgs:
        return ""
    return str(getattr(msgs[-1], "content", ""))


_ALREADY_EXISTED_HINTS = (
    "already covered",
    "already exists",
    "already have",
    "already installed",
    "already registered",
    "no new tool needed",
    "no new tool is needed",
    "covered by the existing",
)


def _looks_like_already_existed(transcript: list[dict], summary: str) -> bool:
    """Heuristic: did the agent decide the gap is already filled by an
    existing tool? Two signals must line up — the agent called
    list_existing_tools (so it actually looked) and the final message
    sounds like 'already covered'. Both conditions guard against false
    positives where the agent just gave up or hit an unrelated error."""
    blob = (summary or "").lower()
    if not any(hint in blob for hint in _ALREADY_EXISTED_HINTS):
        return False
    looked_at_existing = False
    for entry in transcript:
        c = entry.get("content", "")
        if isinstance(c, str) and "list_existing_tools" in c:
            looked_at_existing = True
            break
        # tool messages from list_existing_tools tend to be a JSON array.
        # We don't strictly require the lookup to have happened — the
        # final message hint is the stronger signal — so fall back gracefully.
    return looked_at_existing or "already covered" in blob


def _last_needs_secrets(transcript: list[dict]) -> Optional[dict]:
    """Walk the transcript backwards looking for a tool response that
    declared blocked-on-credentials. Used when the ReAct path tried
    mount_browser_task (or similar) and got back needs_secrets — the UI
    needs that payload to render the credential prompt."""
    for entry in reversed(transcript):
        if entry.get("role") != "tool":
            continue
        content = entry.get("content", "")
        if "\"needs_secrets\"" not in content:
            continue
        try:
            obj = json.loads(content)
        except json.JSONDecodeError:
            continue
        ns = obj.get("needs_secrets")
        if isinstance(ns, dict):
            # Fill in fields the UI's CredentialPrompt expects but the
            # tool may not have populated.
            ns.setdefault("api_name", ns.get("tool_name", ""))
            ns.setdefault("auth", {"type": "browser_session"})
            ns.setdefault(
                "help",
                "Browser tasks need login credentials. They're stored "
                "locally in the vault and only sent to the browser-runner; "
                "never logged.",
            )
            return ns
    return None


def _fallback_stub_code(realized, auth_meta: dict | None = None) -> str:
    """If the Coder can't run, emit a runnable parameter-binding function
    that the adapter exec()s. Honors the auth scheme by adding the secret
    parameter at the end of the signature and wiring it into headers/params."""
    secret_param = (auth_meta or {}).get("secret_key")
    auth_type = (auth_meta or {}).get("type")
    sig_extra = f", {secret_param}: str" if secret_param else ""

    auth_setup = ""
    if auth_type == "bearer_token":
        prefix = (auth_meta or {}).get("prefix", "Bearer ")
        header = (auth_meta or {}).get("header", "Authorization")
        auth_setup = f'    headers[{header!r}] = {prefix!r} + {secret_param}\n'
    elif auth_type == "api_key_header":
        header = (auth_meta or {}).get("header", "X-Api-Key")
        auth_setup = f'    headers[{header!r}] = {secret_param}\n'
    elif auth_type == "api_key_query":
        param = (auth_meta or {}).get("param", "api_key")
        auth_setup = f'    params[{param!r}] = {secret_param}\n'

    return (
        f"async def {realized.tool_name}(**kwargs{sig_extra}):\n"
        f"    import httpx\n"
        f"    url = {realized.invoke_url!r}\n"
        f"    for k in list(kwargs):\n"
        f"        token = '{{' + k + '}}'\n"
        f"        if token in url:\n"
        f"            url = url.replace(token, str(kwargs.pop(k)))\n"
        f"    headers = {{}}\n"
        f"    params = dict(kwargs)\n"
        f"{auth_setup}"
        f"    async with httpx.AsyncClient(timeout=30) as c:\n"
        f"        r = await c.{realized.invoke_method.lower()}(url, params=params, headers=headers)\n"
        f"        r.raise_for_status()\n"
        f"        return r.json()\n"
    )
