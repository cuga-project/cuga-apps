"""Probe harness — the autoresearch keep/discard gate.

Two probe modes:

  probe_realized_tool   — hits the *upstream URL* with httpx using the
                          source's declared sample_input. Cheap; validates
                          the endpoint is reachable and well-shaped.

  probe_executed_code   — exec()s the Coder's *generated Python* against
                          the same sample_input + secrets, then sanity-checks
                          the return value. Phase 3.8: failures here drive
                          the revise loop.

If any probe fails, the proposal is *not* registered and the user sees why.
This is the difference between "the agent generates plausible-looking
tools" and "the agent ships tools that demonstrably work."
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from typing import Any

import httpx

from .sources.base import RealizedTool

log = logging.getLogger(__name__)

_PROBE_TIMEOUT = 15.0
_JUDGE_SYSTEM_PROMPT = """\
You are the probe judge. A tool was just generated and called with a test
input. Inspect the response and decide: does it look like real, useful
data for the tool's stated purpose?

Output JSON only: {"plausible": true|false, "reason": "<short reason>"}.
Be skeptical. If the response is empty, an error message, a 404 page, or
suspiciously generic, output false.
"""


def _format_url(realized: RealizedTool) -> tuple[str, dict, dict]:
    """Return (url, query_params, json_body) for the probe call.

    Path params (e.g. /name/{name}) are substituted from sample_input;
    everything else becomes query string for GET / body for non-GET.
    """
    url = realized.invoke_url or ""
    sample = dict(realized.sample_input or {})
    path_param_re = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    for match in path_param_re.finditer(realized.invoke_url or ""):
        key = match.group(1)
        if key not in sample:
            raise ValueError(f"sample_input missing path param {key!r}")
        url = url.replace(f"{{{key}}}", str(sample.pop(key)))
    method = (realized.invoke_method or "GET").upper()
    if method == "GET":
        return url, sample, {}
    return url, {}, sample


async def probe_realized_tool(
    realized: RealizedTool,
    llm=None,
    timeout: float = _PROBE_TIMEOUT,
    auth: dict | None = None,
    secrets: dict | None = None,
) -> dict:
    """Run the probe + judge cycle. Returns a dict with at minimum:
        ok          bool
        reason      short string
        status_code int (if HTTP call was made)
        response    parsed body (truncated)
        judge       optional dict from LLM judge

    auth + secrets (phase 3.6): if the realized tool needs auth, the probe
    injects the secret into the right place (header / query param) before
    making the call.
    """
    if not realized.invoke_url:
        return {"ok": False, "reason": "no invoke_url to probe"}

    try:
        url, params, body = _format_url(realized)
    except ValueError as exc:
        return {"ok": False, "reason": str(exc)}

    headers: dict[str, str] = {}
    if auth and secrets:
        secret_key = auth.get("secret_key")
        token = (secrets or {}).get(secret_key) if secret_key else None
        if token:
            t = auth.get("type")
            if t == "bearer_token":
                header = auth.get("header", "Authorization")
                prefix = auth.get("prefix", "Bearer ")
                headers[header] = f"{prefix}{token}"
            elif t == "api_key_header":
                header = auth.get("header", "X-Api-Key")
                headers[header] = token
            elif t == "api_key_query":
                params[auth.get("param", "api_key")] = token

    log.info("Probe call: %s %s params(redacted=%d) body=%s",
             realized.invoke_method, url, len(params), body)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(
                realized.invoke_method, url,
                params=params, json=body or None, headers=headers,
            )
    except (httpx.HTTPError, OSError) as exc:
        return {"ok": False, "reason": f"network error: {exc}"}

    structural = _structural_check(r)
    if not structural["ok"]:
        return {**structural, "status_code": r.status_code}

    payload = structural["payload"]
    result = {
        "ok": True,
        "reason": "structural ok",
        "status_code": r.status_code,
        "response": _truncate_payload(payload),
    }

    if llm is not None:
        judge = await _llm_judge(llm, realized, payload)
        result["judge"] = judge
        if not judge.get("plausible"):
            return {**result, "ok": False, "reason": f"judge: {judge.get('reason', 'implausible')}"}
    return result


def _structural_check(response: httpx.Response) -> dict:
    """Cheap, fast: status 200-299, valid JSON body, non-empty payload."""
    if not 200 <= response.status_code < 300:
        return {"ok": False, "reason": f"http {response.status_code}"}
    text = response.text or ""
    if not text.strip():
        return {"ok": False, "reason": "empty response body"}
    try:
        payload: Any = response.json()
    except (json.JSONDecodeError, ValueError):
        return {"ok": False, "reason": "non-JSON response"}
    if payload is None or (isinstance(payload, (list, dict)) and len(payload) == 0):
        return {"ok": False, "reason": "JSON parsed but payload is empty"}
    return {"ok": True, "reason": "structural ok", "payload": payload}


async def _llm_judge(llm, realized: RealizedTool, payload: Any) -> dict:
    """Ask the LLM whether the response is plausibly real data for the
    tool's stated purpose. Forgiving of LLM output noise."""
    excerpt = _truncate_payload(payload)
    user = (
        f"Tool name: {realized.tool_name}\n"
        f"Description: {realized.description}\n"
        f"Sample input: {json.dumps(realized.sample_input)}\n"
        f"Response excerpt:\n{json.dumps(excerpt, indent=2)[:3000]}"
    )
    try:
        # Prefer LangChain message types when available so we get correct
        # role tagging; fall back to plain dicts for stub LLMs in tests.
        try:
            from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore[import-not-found]
            messages = [SystemMessage(content=_JUDGE_SYSTEM_PROMPT), HumanMessage(content=user)]
        except ModuleNotFoundError:
            messages = [
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ]
        resp = await llm.ainvoke(messages)
        text = getattr(resp, "content", "") or ""
        return _parse_judge_output(text)
    except Exception as exc:  # noqa: BLE001
        log.exception("Probe judge failed")
        return {"plausible": True, "reason": f"judge unavailable: {exc} (deferring to structural ok)"}


def _parse_judge_output(text: str) -> dict:
    cleaned = text.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return {"plausible": True, "reason": "judge output unparseable; deferring to structural ok"}
    try:
        obj = json.loads(cleaned[start : end + 1])
        return {"plausible": bool(obj.get("plausible")), "reason": str(obj.get("reason", ""))}
    except json.JSONDecodeError:
        return {"plausible": True, "reason": "judge JSON malformed; deferring to structural ok"}


_EXEC_ALLOWED_TOP_IMPORTS = {
    "httpx", "json", "re", "datetime", "urllib", "asyncio", "typing",
    "math", "base64", "hashlib", "hmac", "uuid", "time",
    "pydantic", "typing_extensions",
}


async def probe_executed_code(
    code: str,
    function_name: str,
    sample_input: dict,
    secrets: dict | None = None,
) -> dict:
    """Phase 3.8 — exec the Coder's output and call the function with the
    sample input + secrets. Returns the same {ok, reason, ...} shape as
    probe_realized_tool. Used by the revise loop.
    """
    # Validate imports cheaply before exec.
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "reason": f"syntax error: {exc}"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                top = n.name.split(".")[0]
                if top not in _EXEC_ALLOWED_TOP_IMPORTS:
                    return {"ok": False, "reason": f"disallowed import: {n.name!r}"}
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top and top not in _EXEC_ALLOWED_TOP_IMPORTS:
                return {"ok": False, "reason": f"disallowed import: from {node.module!r}"}

    namespace: dict = {"__builtins__": __builtins__}
    try:
        exec(compile(tree, f"<probe:{function_name}>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"exec failure: {exc}"}

    func = namespace.get(function_name)
    if func is None or not asyncio.iscoroutinefunction(func):
        return {"ok": False, "reason": f"no async function named {function_name!r} in code"}

    kwargs = {**(sample_input or {}), **(secrets or {})}
    try:
        result = await asyncio.wait_for(func(**kwargs), timeout=_PROBE_TIMEOUT)
    except TypeError as exc:
        return {"ok": False, "reason": f"function signature mismatch: {exc}"}
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "reason": f"upstream http {exc.response.status_code}",
            "status_code": exc.response.status_code,
            "response_excerpt": (exc.response.text or "")[:600],
        }
    except (httpx.HTTPError, OSError) as exc:
        return {"ok": False, "reason": f"network error: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"runtime error: {exc!r}"}

    if result is None:
        return {"ok": False, "reason": "function returned None"}
    if isinstance(result, (list, dict)) and len(result) == 0:
        return {"ok": False, "reason": "function returned empty payload"}

    return {
        "ok": True,
        "reason": "executed code passed",
        "response": _truncate_payload(result),
    }


def _truncate_payload(payload: Any, max_chars: int = 1500) -> Any:
    """Cut huge responses down to something log/judgable, preserving shape."""
    text = json.dumps(payload)
    if len(text) <= max_chars:
        return payload
    if isinstance(payload, list):
        return payload[:3] + [f"... ({len(payload) - 3} more items omitted)"]
    if isinstance(payload, dict):
        keys = list(payload.keys())[:8]
        out = {k: payload[k] for k in keys}
        out["...truncated"] = f"{len(payload) - len(keys)} more keys"
        return out
    return text[:max_chars] + "..."
