"""
_ratelimit.py — shared, dependency-free rate limiting for the cuga-apps.

These apps are deployed publicly on Code Engine. The expensive surface is the
agent endpoint (POST /ask and friends): every call fans out to an LLM and the
open web. Without limits, one client can bombard a single app — burning cost
and starving real users. This installs layered, in-memory limits with one call:

    from _ratelimit import install_rate_limit
    install_rate_limit(app)        # call once, before uvicorn.run(app, ...)

Design — five cheap layers, applied to POST requests by default (GET is left
free: that's the UI, /health, and the /session polling the right panel does
every 10s). Layers run cheap-first:

  1. Body-size cap     — reject oversized prompts before doing any work.
  2. Per-IP token bucket — sustained rate + a small burst, per client IP.
  3. Per-IP daily cap  — a hard ceiling per client per day.
  4. Global token bucket — backstop on total throughput across ALL IPs, so an
                           attacker rotating IPs still can't run up cost.
  5. Concurrency gate  — max simultaneous in-flight POSTs (each app is one CE
                         instance at --max-scale 1, so this is authoritative).

Because each app runs as a single instance (deploy_apps.sh uses --max-scale 1),
in-memory state is authoritative — no Redis/Memcached needed. Everything is
tunable via env vars, so you change limits by editing the CE `app-env` secret
and restarting — no code change, no rebuild:

  RL_ENABLED          "1"       master switch ("0" disables all limiting)
  RL_PER_MIN          "30"      sustained POSTs per minute per IP
  RL_BURST            "12"      token-bucket capacity (short burst) per IP
  RL_PER_DAY          "300"     hard POSTs per day per IP        (0 = off)
  RL_GLOBAL_PER_MIN   "150"     POSTs per minute across all IPs  (0 = off)
  RL_CONCURRENCY      "6"       max concurrent POSTs             (0 = off)
  RL_MAX_BODY_BYTES   "32768"   reject POST bodies larger than this (0 = off)
  RL_TRUST_FORWARDED  "1"       derive client IP from X-Forwarded-For (CE/proxy)
  RL_MAX_TRACKED_IPS  "20000"   LRU cap on the per-IP table (bounds memory)
  RL_METHODS          "POST"    comma-separated methods to guard
  RL_EXEMPT_PATHS     "/health" comma-separated path prefixes never limited

Denials return HTTP 429 (or 413 for oversize) with a Retry-After header and a
JSON body shaped `{"answer": "<friendly message>", "thread_id": ""}` so the
existing chat UIs render the message inline instead of a raw error.

NOTE on client IP: behind Code Engine the real client is in X-Forwarded-For
(leftmost). That header is spoofable, so per-IP limits are a deterrent, not a
hard guarantee — the global + concurrency + body caps are the spoof-proof
backstops on actual cost. For a hard guarantee, front the apps with IBM Cloud
Internet Services (CIS) WAF / API Gateway rate limiting (see module footer).
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class _TokenBucket:
    """Classic token bucket. capacity = max burst; rate = tokens/sec refill."""
    __slots__ = ("tokens", "cap", "rate", "last")

    def __init__(self, capacity: float, rate_per_sec: float) -> None:
        self.cap = float(capacity)
        self.rate = float(rate_per_sec)
        self.tokens = float(capacity)
        self.last = time.monotonic()

    def take(self, now: float) -> tuple[bool, float]:
        """Try to consume one token. Returns (allowed, retry_after_seconds)."""
        self.tokens = min(self.cap, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0.0
        retry = (1.0 - self.tokens) / self.rate if self.rate > 0 else 3600.0
        return False, retry


class _Config:
    def __init__(self, **kw) -> None:
        self.enabled = os.getenv("RL_ENABLED", "1") != "0"
        self.per_min = _env_int("RL_PER_MIN", 30)
        self.burst = _env_int("RL_BURST", 12)
        self.per_day = _env_int("RL_PER_DAY", 300)
        self.global_per_min = _env_int("RL_GLOBAL_PER_MIN", 150)
        self.concurrency = _env_int("RL_CONCURRENCY", 6)
        self.max_body = _env_int("RL_MAX_BODY_BYTES", 32768)
        self.trust_forwarded = os.getenv("RL_TRUST_FORWARDED", "1") != "0"
        self.max_tracked = _env_int("RL_MAX_TRACKED_IPS", 20000)
        self.methods = {m.strip().upper() for m in
                        os.getenv("RL_METHODS", "POST").split(",") if m.strip()}
        self.exempt = tuple(p.strip() for p in
                            os.getenv("RL_EXEMPT_PATHS", "/health").split(",") if p.strip())
        # Per-call overrides win over env (lets an app tighten/loosen itself).
        for k, v in kw.items():
            setattr(self, k, v)


def _client_ip(request, trust_forwarded: bool) -> str:
    if trust_forwarded:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        xri = request.headers.get("x-real-ip")
        if xri:
            return xri.strip()
    return request.client.host if request.client else "unknown"


class _Limiter:
    def __init__(self, cfg: _Config) -> None:
        self.cfg = cfg
        self._ips: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()
        self._global = (_TokenBucket(cfg.global_per_min, cfg.global_per_min / 60.0)
                        if cfg.global_per_min > 0 else None)
        self._sem = None  # created lazily once an event loop is running

    def _deny(self, status: int, message: str, retry_after: float | None):
        from fastapi.responses import JSONResponse
        headers = {}
        if retry_after and retry_after > 0:
            headers["Retry-After"] = str(int(retry_after) + 1)
        return JSONResponse(status_code=status,
                            content={"answer": message, "thread_id": ""},
                            headers=headers)

    def _check_counters(self, ip: str):
        """Per-IP + global checks. Returns a deny-response, or None to allow.
        Runs under the lock; no awaits inside."""
        cfg = self.cfg
        now = time.monotonic()
        wall = time.time()
        day_key = int(wall // 86400)
        rec = self._ips.get(ip)
        if rec is None:
            rec = {"bucket": _TokenBucket(cfg.burst, cfg.per_min / 60.0),
                   "day_count": 0, "day_key": day_key}
            self._ips[ip] = rec
        self._ips.move_to_end(ip)

        if day_key != rec["day_key"]:
            rec["day_key"] = day_key
            rec["day_count"] = 0
        if cfg.per_day > 0 and rec["day_count"] >= cfg.per_day:
            secs_to_midnight = 86400 - int(wall % 86400)
            return self._deny(429, "You've reached today's request limit for this "
                              "app. Please try again tomorrow.", secs_to_midnight)

        ok, retry = rec["bucket"].take(now)
        if not ok:
            return self._deny(429, "You're sending requests too quickly. "
                              "Please wait a few seconds and try again.", retry)

        if self._global is not None:
            gok, gretry = self._global.take(now)
            if not gok:
                return self._deny(429, "This app is busy right now. "
                                  "Please try again in a moment.", gretry)

        rec["day_count"] += 1
        # Bound memory: evict least-recently-seen IPs over the cap.
        while len(self._ips) > cfg.max_tracked:
            self._ips.popitem(last=False)
        return None

    async def handle(self, request, call_next):
        cfg = self.cfg
        path = request.url.path
        if (request.method not in cfg.methods
                or any(path.startswith(p) for p in cfg.exempt)):
            return await call_next(request)

        # 1. Body-size cap (cheap, header-only).
        if cfg.max_body > 0:
            cl = request.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > cfg.max_body:
                return self._deny(413, "Your request is too large. "
                                  "Please shorten your message.", None)

        # 2–4. Per-IP + global counters (under lock).
        ip = _client_ip(request, cfg.trust_forwarded)
        with self._lock:
            denied = self._check_counters(ip)
        if denied is not None:
            return denied

        # 5. Concurrency gate.
        if cfg.concurrency > 0:
            import asyncio
            if self._sem is None:
                self._sem = asyncio.Semaphore(cfg.concurrency)
            try:
                await asyncio.wait_for(self._sem.acquire(), timeout=0.01)
            except asyncio.TimeoutError:
                return self._deny(429, "This app is handling several requests "
                                  "right now. Please retry in a few seconds.", 5)
            try:
                return await call_next(request)
            finally:
                self._sem.release()

        return await call_next(request)


def install_rate_limit(app, **overrides) -> None:
    """Install layered rate limiting on a FastAPI app. Idempotent per app.

    Call once, before serving (e.g. right before uvicorn.run(app, ...)). Pass
    keyword overrides (e.g. per_min=30) to override the env defaults for a
    specific app — useful for a heavier app that wants a tighter cap.
    """
    if getattr(app.state, "_rate_limit_installed", False):
        return
    cfg = _Config(**overrides)
    if not cfg.enabled:
        return
    limiter = _Limiter(cfg)

    @app.middleware("http")
    async def _rate_limit_mw(request, call_next):
        try:
            return await limiter.handle(request, call_next)
        except Exception:  # noqa: BLE001 — limiter must never break the app
            return await call_next(request)

    app.state._rate_limit_installed = True


# ─────────────────────────────────────────────────────────────────────────
# Defense-in-depth beyond this module (recommended for a public deployment):
#
#   • IBM Cloud Internet Services (CIS): put the apps behind a CIS-proxied
#     hostname and enable WAF + Rate Limiting rules (e.g. 30 req/min/IP on
#     /ask). This is edge-enforced and not spoofable, unlike X-Forwarded-For.
#   • API Gateway / app-id: require a key or auth in front of /ask if you want
#     to gate to known users while keeping the read-only UI public.
#   • Code Engine scaling: keep --max-scale modest so a flood can't fan out
#     into unbounded concurrency/cost (deploy_apps.sh already pins max-scale 1).
# ─────────────────────────────────────────────────────────────────────────
