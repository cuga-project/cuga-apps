"""_chrome.py — shared UI chrome injected into every cuga-app's HTML page.

Every app calls ``install_usage(app)`` (see _usage.py), which calls
``install_chrome(app)`` here. A single response middleware rewrites
``text/html`` GET responses to add, consistently across all ~33 apps:

  • a privacy "heads up" banner pinned to the top (public demo; requests logged)
  • the LLM model the app runs on + an MCP Tool Explorer link, placed INSIDE the
    app's own tools row (the ``.app-intro__tools`` chip strip that 21 apps share)
    so they sit with the other tool pills — not in the top banner. Apps without
    that row get a small fallback badge instead.

Doing it in ONE place beats hand-editing 33 heterogeneous app UIs and keeps
them identical. Only ``text/html`` is rewritten — JSON and ``text/event-stream``
(SSE) pass through untouched, so streaming endpoints are never buffered.
"""
from __future__ import annotations

import html as _html
import os
import re

_MARKER = "cuga-chrome"                       # banner id — also the idempotency guard
# The shared tools strip in app-intro headers; its children are <span> pills, so
# the first </div> after the opening tag is the row's closer (safe to target).
_TOOLS_ROW_RE = re.compile(r'(<div class="app-intro__tools">.*?)(</div>)',
                           re.DOTALL | re.IGNORECASE)
_BODY_RE = re.compile(r"<body[^>]*>", re.IGNORECASE)

# Public MCP Tool Explorer (standalone Code Engine app). Override per deployment
# with MCP_TOOL_EXPLORER_URL (e.g. a localhost port for local dev).
_DEFAULT_EXPLORER = ("https://cuga-apps-mcp-tool-explorer."
                     "1gxwxi8kos9y.us-east.codeengine.appdomain.cloud")

_PRIVACY = ("Heads up: these are public demo apps. Your requests are logged for "
            "usage analytics — please don't enter confidential information, "
            "credentials, or personal data.")


def _model_label() -> str:
    model = (os.getenv("LLM_MODEL") or "").strip()
    provider = (os.getenv("LLM_PROVIDER") or "").strip()
    short = model.split("/")[-1] if model else ""   # drop an "openai/" routing prefix
    if short and provider:
        return f"{short} · {provider}"
    return short or provider or "—"


def _explorer_url() -> str:
    return (os.getenv("MCP_TOOL_EXPLORER_URL") or _DEFAULT_EXPLORER).rstrip("/")


# ── Top banner — privacy notice only (compliance; stays pinned at the top) ──
def _banner_fragment() -> str:
    privacy = _html.escape(_PRIVACY)
    return (
        "<style>"
        "body{padding-top:40px !important}"
        f"#{_MARKER}{{position:fixed;top:0;left:0;right:0;z-index:2147483600;"
        "padding:6px 14px;background:#fcf4d6;border-bottom:1px solid #e8c95a;"
        "color:#5b4a14;font:500 12px/1.35 -apple-system,system-ui,'Segoe UI',Roboto,sans-serif}"
        f"#{_MARKER} .cc-msg{{display:block}}"
        # Pills injected into the app's tools row (mostly inherit .tool-pill;
        # these rules just guarantee a sane look if the app styles it loosely).
        ".cuga-tool-pill{text-decoration:none;color:inherit;white-space:nowrap}"
        ".cuga-tool-pill:hover{text-decoration:underline}"
        # Fallback badge for apps with no tools row.
        f".{_MARKER}-badge{{position:fixed;left:10px;bottom:10px;z-index:2147483600;"
        "display:flex;gap:8px;align-items:center;padding:4px 10px;border-radius:6px;"
        "background:#fff7e0;border:1px solid #e8c95a;color:#5b4a14;"
        "font:500 11px/1.3 ui-monospace,Menlo,monospace}"
        f".{_MARKER}-badge a{{color:#0f62fe;font-weight:600;text-decoration:none}}"
        "</style>"
        f'<div id="{_MARKER}"><span class="cc-msg">{privacy}</span></div>'
    )


# ── Model + MCP Tools — as native pills inside the app's tools row ──────────
def _tool_pills() -> str:
    model = _html.escape(_model_label())
    explorer = _html.escape(_explorer_url())
    return (
        f'<span class="tool-pill cuga-tool-pill" '
        f'title="LLM model this app is running on">🧠 {model}</span>'
        f'<a class="tool-pill cuga-tool-pill" href="{explorer}" target="_blank" '
        f'rel="noopener noreferrer" title="Browse &amp; invoke every MCP tool '
        f'across all servers">🛠 MCP Tools ↗</a>'
    )


def _badge_fragment() -> str:
    model = _html.escape(_model_label())
    explorer = _html.escape(_explorer_url())
    return (
        f'<div class="{_MARKER}-badge">'
        f'<span title="LLM model this app is running on">🧠 {model}</span>'
        f'<a href="{explorer}" target="_blank" rel="noopener noreferrer">🛠 MCP Tools ↗</a>'
        "</div>"
    )


def _inject(markup: str) -> str:
    if _MARKER in markup:
        return markup                               # idempotent — already injected

    # 1) privacy banner right after <body>
    frag = _banner_fragment()
    m = _BODY_RE.search(markup)
    markup = (markup[:m.end()] + frag + markup[m.end():]) if m else (frag + markup)

    # 2) model + MCP Tools into the app's tools row, else a fallback badge
    pills = _tool_pills()
    markup, n = _TOOLS_ROW_RE.subn(lambda mm: mm.group(1) + pills + mm.group(2),
                                   markup, count=1)
    if n == 0:
        badge = _badge_fragment()
        bm = re.search(r"</body>", markup, re.IGNORECASE)
        markup = (markup[:bm.start()] + badge + markup[bm.start():]) if bm else markup + badge
    return markup


def install_chrome(app) -> None:
    """Add the HTML-injection middleware to a FastAPI/Starlette app.

    Idempotent per app, and best-effort — it must never raise into the app.
    """
    if getattr(getattr(app, "state", None), "_cuga_chrome_installed", False):
        return
    try:
        from starlette.responses import Response
    except Exception:
        return

    @app.middleware("http")
    async def _chrome_mw(request, call_next):
        response = await call_next(request)
        # Only rewrite full HTML GET pages. SSE (text/event-stream) and JSON
        # pass straight through, so streaming endpoints are never buffered.
        if request.method != "GET":
            return response
        ctype = response.headers.get("content-type", "")
        if "text/html" not in ctype.lower():
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode()
        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers.pop("content-type", None)
        try:
            out = _inject(body.decode("utf-8", "replace")).encode("utf-8")
        except Exception:
            out = body
        return Response(content=out, status_code=response.status_code,
                        headers=headers, media_type=ctype or "text/html; charset=utf-8")

    try:
        app.state._cuga_chrome_installed = True
    except Exception:
        pass
