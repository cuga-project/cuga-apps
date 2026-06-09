"""
_usage.py — shared usage-tracking client for the cuga-apps.

Goal: know whether each app is actually being used — aggregate counts, not
identities. Install once per app (same pattern as _ratelimit):

    from _usage import install_usage
    install_usage(app)            # call once, before uvicorn.run(app, ...)

Per request it does two cheap things, after the response is produced:
  1. Logs a structured JSON line to stdout (durable — Code Engine captures it).
  2. Fire-and-forgets a tiny ping to the central collector (USAGE_COLLECTOR_URL)
     so a single dashboard can roll up usage across every app.

Privacy: there is no account/login. The only identity is `visitor` — a
DAILY-SALTED hash of the client IP (sha256(salt | UTC-day | ip)[:16]). It lets
the collector count unique visitors *per day* without storing an IP or anything
that links a person across days.

Tracking is best-effort and must NEVER affect the app: the ping is fire-and-
forget with a short timeout and all errors are swallowed. If
USAGE_COLLECTOR_URL is unset, it just logs to stdout (no ping) — so apps run
fine standalone.

Env:
  USAGE_COLLECTOR_URL   e.g. http://127.0.0.1:28827/track  (unset = stdout only)
  USAGE_TOKEN           shared secret sent as X-Usage-Token (match the collector)
  USAGE_SALT            anonymization salt (default "cuga-usage")
  USAGE_METHODS         methods to count (default "POST" — the agent calls)
  RL_TRUST_FORWARDED    "1" → derive client IP from X-Forwarded-For (CE/proxy)
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import uuid

log = logging.getLogger("usage")

_COLLECTOR_URL = os.getenv("USAGE_COLLECTOR_URL", "").strip()
_TOKEN = os.getenv("USAGE_TOKEN", "").strip()
_SALT = os.getenv("USAGE_SALT", "cuga-usage")
_TRUST_FWD = os.getenv("RL_TRUST_FORWARDED", "1") != "0"
_METHODS = {m.strip().upper() for m in os.getenv("USAGE_METHODS", "POST").split(",") if m.strip()}
# Cap on stored utterance length (chars) — keep pings tiny and bound storage.
_UTT_MAX = int(os.getenv("USAGE_UTTERANCE_MAXLEN", "2000"))
# Never count infra/poll/collector endpoints.
_EXEMPT = ("/health", "/usage", "/api/stats", "/track", "/favicon", "/static")

_client = None  # lazy httpx.AsyncClient, created on the running loop

# Correlation id for the in-flight utterance. track_utterance() sets it;
# track_call() reads it so IN-PROCESS provider calls (the LLM, via _llm.py's
# LangChain callback) are attributed to the utterance that triggered them.
# A ContextVar gives per-request isolation under asyncio (each request handler
# runs in its own task with its own copy). Cross-process callers — the MCP
# servers (tavily, geo, …) — never set it, so their calls stay unattributed
# (aggregate-only), which is exactly what we want for "LLM-exact" attribution.
_CUR_UTT: contextvars.ContextVar = contextvars.ContextVar("cuga_utt_id", default=None)


def _app_name(app) -> str:
    # Apps launch as `python <dir>/main.py` (or run.py), so the entrypoint's
    # parent dir is the app name. Fall back to the FastAPI title.
    try:
        d = os.path.basename(os.path.dirname(os.path.abspath(sys.argv[0])))
        if d and d not in ("", "apps"):
            return d
    except Exception:  # noqa: BLE001
        pass
    return getattr(app, "title", "app") or "app"


def _client_ip(request) -> str:
    if _TRUST_FWD:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip")
        if xri:
            return xri.strip()
    return request.client.host if request.client else "unknown"


def _visitor(ip: str) -> str:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    return hashlib.sha256(f"{_SALT}|{day}|{ip}".encode()).hexdigest()[:16]


async def _send(event: dict) -> None:
    global _client
    if not _COLLECTOR_URL:
        return
    try:
        import httpx
        if _client is None:
            _client = httpx.AsyncClient(timeout=2.0)
        headers = {"X-Usage-Token": _TOKEN} if _TOKEN else {}
        await _client.post(_COLLECTOR_URL, json=event, headers=headers)
    except Exception:  # noqa: BLE001 — tracking must never break the app
        pass


def _send_sync(event: dict) -> None:
    """Blocking POST used when there's no running event loop (sync callers)."""
    if not _COLLECTOR_URL:
        return
    try:
        import httpx
        headers = {"X-Usage-Token": _TOKEN} if _TOKEN else {}
        httpx.post(_COLLECTOR_URL, json=event, headers=headers, timeout=2.0)
    except Exception:  # noqa: BLE001 — tracking must never break the app
        pass


def _emit(event: dict) -> None:
    """Fire-and-forget an event from either an async or a sync context.

    Always logs to stdout (durable on Code Engine), then pings the collector
    without ever blocking the caller: on the running loop via a task, otherwise
    on a short-lived daemon thread. All transport errors are swallowed.
    """
    try:
        log.info("usage %s", json.dumps(event))
    except Exception:  # noqa: BLE001
        pass
    if not _COLLECTOR_URL:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(event))
    except RuntimeError:                      # no running loop → sync path
        threading.Thread(target=_send_sync, args=(event,), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass


_APP_NAME_CACHE: str | None = None


def _detect_app_name() -> str:
    global _APP_NAME_CACHE
    if _APP_NAME_CACHE is None:
        try:
            d = os.path.basename(os.path.dirname(os.path.abspath(sys.argv[0])))
            _APP_NAME_CACHE = d if d and d not in ("", "apps") else "app"
        except Exception:  # noqa: BLE001
            _APP_NAME_CACHE = "app"
    return _APP_NAME_CACHE


# Redact obvious secrets users might paste into a prompt before we store the
# text. Best-effort, not a guarantee — the umbrella UI also warns users.
_SECRET_RE = re.compile(
    r"\b("
    r"sk-[A-Za-z0-9]{16,}"             # OpenAI-style
    r"|tvly-[A-Za-z0-9]{8,}"           # Tavily
    r"|AKIA[0-9A-Z]{12,}"              # AWS access key id
    r"|xox[baprs]-[A-Za-z0-9-]{8,}"    # Slack
    r"|gh[pousr]_[A-Za-z0-9]{20,}"     # GitHub
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}"  # JWT
    r"|[A-Za-z0-9+/_-]{40,}"           # long opaque token blobs
    r")\b"
)


def _scrub(text: str) -> str:
    return _SECRET_RE.sub("«redacted»", text)


def classify_error(exc: object) -> str:
    """Best-effort short failure code for a provider call: the HTTP status
    ("429", "404", "503", …) when the exception carries a response, else a
    coarse label ("timeout", "connection", or the exception class name)."""
    try:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status:
            return str(status)
        name = type(exc).__name__.lower()
        if "timeout" in name:
            return "timeout"
        if "connect" in name:
            return "connection"
        return name[:24] or "error"
    except Exception:  # noqa: BLE001
        return "error"


def track_call(provider: str, *, app: str | None = None, ok: bool = True,
               n: int = 1, code: str | None = None) -> None:
    """Count an external/provider API call (tavily, alpha_vantage, watsonx, …).

    On failure pass `code` — an HTTP status ("429", "404") or short label — so
    the dashboard can show *why* calls failed (e.g. how often a rate limit was
    hit). Use classify_error(exc) to derive it from an exception.

    Fire-and-forget and safe from any context (async app handlers, sync MCP
    tools, LangChain callbacks). Never raises.
    """
    try:
        event = {"kind": "call", "provider": str(provider)[:40],
                 "app": app or _detect_app_name(), "ok": bool(ok),
                 "n": int(n), "ts": time.time()}
        if not ok and code:
            event["code"] = str(code)[:24]
        utt = _CUR_UTT.get()
        if utt:                       # set only for in-process LLM calls
            event["utt"] = utt
        _emit(event)
    except Exception:  # noqa: BLE001
        pass


def track_utterance(text: str, *, app: str | None = None) -> str | None:
    """Record a user's natural-language input (chat utterance) for the dashboard.

    Truncates to USAGE_UTTERANCE_MAXLEN and scrubs obvious secrets before it
    leaves the process. Also sets the per-utterance correlation id (_CUR_UTT) so
    subsequent in-process provider calls (the LLM) attribute to this utterance.
    Returns that id (callers may ignore it). Fire-and-forget; never raises.
    """
    try:
        if not text:
            return None
        clean = _scrub(str(text).strip())[:_UTT_MAX]
        if not clean:
            return None
        uid = uuid.uuid4().hex[:12]
        _CUR_UTT.set(uid)
        _emit({"kind": "utterance", "id": uid, "app": app or _detect_app_name(),
               "text": clean, "ts": time.time()})
        return uid
    except Exception:  # noqa: BLE001
        return None


def install_usage(app, app_name: str | None = None) -> None:
    """Install usage tracking on a FastAPI app. Idempotent per app."""
    if getattr(app.state, "_usage_installed", False):
        return
    name = app_name or _app_name(app)

    @app.middleware("http")
    async def _usage_mw(request, call_next):
        response = await call_next(request)
        try:
            path = request.url.path
            if (request.method in _METHODS
                    and not any(path.startswith(p) for p in _EXEMPT)):
                event = {
                    "app":     name,
                    "event":   path,
                    "method":  request.method,
                    "status":  response.status_code,
                    "visitor": _visitor(_client_ip(request)),
                    "ts":      time.time(),
                }
                log.info("usage %s", json.dumps(event))      # durable via stdout
                asyncio.create_task(_send(event))             # best-effort ping
        except Exception:  # noqa: BLE001
            pass
        return response

    app.state._usage_installed = True
