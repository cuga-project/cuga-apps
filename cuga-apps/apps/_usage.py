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
import hashlib
import json
import logging
import os
import sys
import time

log = logging.getLogger("usage")

_COLLECTOR_URL = os.getenv("USAGE_COLLECTOR_URL", "").strip()
_TOKEN = os.getenv("USAGE_TOKEN", "").strip()
_SALT = os.getenv("USAGE_SALT", "cuga-usage")
_TRUST_FWD = os.getenv("RL_TRUST_FORWARDED", "1") != "0"
_METHODS = {m.strip().upper() for m in os.getenv("USAGE_METHODS", "POST").split(",") if m.strip()}
# Never count infra/poll/collector endpoints.
_EXEMPT = ("/health", "/usage", "/api/stats", "/track", "/favicon", "/static")

_client = None  # lazy httpx.AsyncClient, created on the running loop


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
