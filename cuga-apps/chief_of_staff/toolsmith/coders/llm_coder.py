"""LLMCoder — wraps a LangChain BaseChatModel with a code-gen prompt.

Defaults to RITS gpt-oss-120b but uses TOOLSMITH_CODER_PROVIDER /
TOOLSMITH_CODER_MODEL env if set. Reuses apps/_llm.create_llm so we
don't reinvent provider plumbing.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from .base import CodeGenResult, CodeGenSpec, CoderClient, ProbeFailure

log = logging.getLogger(__name__)

# Make apps/_llm.py importable.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent.parent
_APPS_DIR = _REPO_ROOT / "apps"
for _p in (str(_APPS_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


_SYSTEM_PROMPT = """\
You are a code generator. Produce ONE Python async function that wraps the
described API endpoint. Output ONLY the function source — no prose, no
imports outside the function body, no markdown fences.

Constraints:
- The function MUST be `async def <name>(...)`.
- Use `httpx.AsyncClient` for HTTP calls. Import httpx INSIDE the function.
- Substitute `{path_param}` placeholders from the function arguments.
- Pass non-path arguments as query params for GET, JSON body otherwise.
- Return the parsed JSON response.
- Do NOT swallow exceptions; let them propagate.
- Keep it under 40 lines.

If an `Auth` section is provided, the function MUST accept the listed secret
parameters as additional keyword arguments AT THE END of the signature (after
the user-facing parameters), and use them according to the auth scheme:
  - bearer_token   : add `headers["Authorization"] = "<prefix><token>"`
  - api_key_header : add `headers["<header>"] = <key>`
  - api_key_query  : add the secret to params under `<param>`

You'll be given the function name, parameter schema, base URL, method, path,
optional auth scheme, and a one-line description.
"""


_REVISE_PROMPT = """\
The prior code failed its probe. Here's the failure reason:

{reason}
Status code: {status}
Response excerpt: {excerpt}
Judge feedback: {judge}

Rewrite the function to address the failure. Output ONLY the function source.
"""


class LLMCoder(CoderClient):
    name = "gpt_oss"

    def __init__(self, llm=None):
        if llm is None:
            llm = _build_default_llm()
        self._llm = llm

    @property
    def llm(self):
        return self._llm

    async def generate_tool(self, spec: CodeGenSpec) -> CodeGenResult:
        prompt = _format_spec_prompt(spec)
        text = await self._invoke(_SYSTEM_PROMPT, prompt)
        code = _extract_code(text)
        return CodeGenResult(code=code, notes="")

    async def revise_tool(self, prior: CodeGenResult, feedback: ProbeFailure) -> CodeGenResult:
        revise_msg = _REVISE_PROMPT.format(
            reason=feedback.reason,
            status=feedback.status_code,
            excerpt=feedback.response_excerpt[:1000],
            judge=feedback.judge_feedback or "(none)",
        ) + "\n\nPrior code:\n```python\n" + prior.code + "\n```"
        text = await self._invoke(_SYSTEM_PROMPT, revise_msg)
        return CodeGenResult(code=_extract_code(text), notes="revision")

    async def _invoke(self, system: str, user: str) -> str:
        if self._llm is None:
            raise RuntimeError("LLMCoder has no LLM configured")
        try:
            from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore[import-not-found]
            messages = [SystemMessage(content=system), HumanMessage(content=user)]
        except ModuleNotFoundError:
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        resp = await self._llm.ainvoke(messages)
        return getattr(resp, "content", "") or ""


def _build_default_llm():
    provider = os.environ.get("TOOLSMITH_CODER_PROVIDER") or os.environ.get(
        "TOOLSMITH_LLM_PROVIDER", "rits"
    )
    model = os.environ.get("TOOLSMITH_CODER_MODEL") or os.environ.get(
        "TOOLSMITH_LLM_MODEL", "gpt-oss-120b"
    )
    try:
        from _llm import create_llm  # type: ignore[import-not-found]
        return create_llm(provider=provider, model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLMCoder default LLM unavailable (provider=%s model=%s): %s",
                    provider, model, exc)
        return None


def _format_spec_prompt(spec: CodeGenSpec) -> str:
    # Some upstream sources hand us flattened schemas where the value is a
    # bare type string (e.g. {"symbol": "string"}) instead of the JSON-Schema
    # shape ({"symbol": {"type": "string", ...}}). Coerce so .get() never
    # blows up — without this the ReAct path crashed mid-codegen and only
    # the deterministic fallback succeeded.
    def _normalize(info: object) -> dict:
        if isinstance(info, dict):
            return info
        if isinstance(info, str):
            return {"type": info, "description": ""}
        return {"type": "string", "description": ""}

    parts = [
        f"Function name: {spec.name}",
        f"Description: {spec.description}",
        "Parameters:",
        *(
            f"  - {p}: {n.get('type', 'string')}"
            f" {'(required)' if n.get('required') else '(optional)'}"
            f" — {n.get('description', '')}"
            for p, info in (spec.parameters_schema or {}).items()
            for n in (_normalize(info),)
        ),
    ]
    if spec.api_base_url:
        parts.append(f"Base URL: {spec.api_base_url}")
    parts.append(f"Method: {spec.api_method}")
    if spec.api_path:
        parts.append(f"Path: {spec.api_path}")
    if spec.auth:
        a = spec.auth
        parts.append("\nAuth:")
        parts.append(f"  type: {a.get('type')}")
        parts.append(f"  secret_param_name: {a.get('secret_key')}")
        if a.get("header"):
            parts.append(f"  header: {a['header']}")
        if a.get("param"):
            parts.append(f"  param: {a['param']}")
        if a.get("prefix"):
            parts.append(f"  prefix: {a['prefix']!r}")
        parts.append(f"  → add `{a.get('secret_key')}: str` AT THE END of the signature.")
    if spec.expected_output_shape:
        parts.append(f"Expected output shape: {spec.expected_output_shape}")
    if spec.extra_context:
        parts.append(f"Additional context:\n{spec.extra_context}")
    return "\n".join(parts)


_FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.DOTALL)


def _extract_code(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()
