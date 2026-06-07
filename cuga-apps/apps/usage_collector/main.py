"""
Usage Collector — cross-app usage dashboard for the cuga-apps.

Every app installs _usage.py, which fire-and-forgets a tiny ping per request to
this collector's POST /track. The collector aggregates those into per-app,
per-day counters and serves a single dashboard (GET /) answering the question
"are people actually using these apps?" — requests, unique visitors/day, and
last-seen, across every app.

Why a separate always-on app: the other apps scale to zero, so in-memory counts
there are lost on cold start. This one runs at --max-scale/--min-scale 1 and
persists a snapshot durably, so the history survives restarts.

Anonymized by design: it only ever sees `visitor` = a daily-salted hash of the
client IP (computed in _usage.py). No IPs, no PII.

Persistence (snapshot of the aggregates, JSON):
  • default      — a local file at USAGE_DB_PATH (good for docker w/ a volume;
                   ephemeral on Code Engine, survives only while the instance
                   lives — which, at min-scale 1, is "until next redeploy").
  • durable      — IBM Cloud Object Storage / any S3: set USAGE_S3_BUCKET (+
                   USAGE_S3_ENDPOINT for COS) and AWS_ACCESS_KEY_ID /
                   AWS_SECRET_ACCESS_KEY. Snapshot is written there periodically
                   and on shutdown, and loaded on startup.

Security: POST /track requires header X-Usage-Token == USAGE_TOKEN (if set).
The dashboard requires ?token=<USAGE_DASHBOARD_TOKEN> (if set).

Run:
    python main.py --port 28827

Env:
  USAGE_TOKEN            shared secret apps must send to /track  (recommended)
  USAGE_DASHBOARD_TOKEN  if set, dashboard + /api/stats require ?token=...
  USAGE_DB_PATH          local snapshot path (default /tmp/usage_db.json)
  USAGE_S3_BUCKET        S3/COS bucket for durable snapshots (optional)
  USAGE_S3_ENDPOINT      S3/COS endpoint URL (required for COS)
  USAGE_S3_KEY           object key (default "usage_db.json")
  AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   S3/COS HMAC creds
  USAGE_SAVE_INTERVAL    seconds between background snapshots (default 60)
  USAGE_MAX_VISITORS_DAY cap on tracked unique hashes per app/day (default 200000)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("usage_collector")

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ui import _HTML

_TOKEN = os.getenv("USAGE_TOKEN", "").strip()
_DASH_TOKEN = os.getenv("USAGE_DASHBOARD_TOKEN", "").strip()
_DB_PATH = os.getenv("USAGE_DB_PATH", "/tmp/usage_db.json")
_S3_BUCKET = os.getenv("USAGE_S3_BUCKET", "").strip()
_S3_ENDPOINT = os.getenv("USAGE_S3_ENDPOINT", "").strip()
_S3_KEY = os.getenv("USAGE_S3_KEY", "usage_db.json")
_SAVE_INTERVAL = int(os.getenv("USAGE_SAVE_INTERVAL", "60"))
_MAX_VISITORS = int(os.getenv("USAGE_MAX_VISITORS_DAY", "200000"))


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Aggregate store ──────────────────────────────────────────────────────
# stats[app][day] = {"requests": int, "uniques": set[str],
#                    "statuses": {code: int}, "last_ts": float}
class _Store:
    def __init__(self) -> None:
        self._stats: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(self._blank))
        self._lock = threading.Lock()
        self._dirty = False

    @staticmethod
    def _blank() -> dict:
        return {"requests": 0, "uniques": set(), "statuses": defaultdict(int), "last_ts": 0.0}

    def record(self, app: str, day: str, visitor: str, status: int, ts: float) -> None:
        with self._lock:
            rec = self._stats[app][day]
            rec["requests"] += 1
            if visitor and len(rec["uniques"]) < _MAX_VISITORS:
                rec["uniques"].add(visitor)
            rec["statuses"][str(status)] += 1
            rec["last_ts"] = max(rec["last_ts"], ts)
            self._dirty = True

    def rollup(self, days: int = 14) -> dict:
        """Per-app summary + a daily series for the last `days` days."""
        with self._lock:
            today = _today()
            recent = [(datetime.now(timezone.utc).date().toordinal() - i) for i in range(days)]
            recent_days = [datetime.fromordinal(o).strftime("%Y-%m-%d") for o in sorted(recent)]
            apps = []
            tot_req = tot_today = tot_uniq_today = 0
            for app, by_day in self._stats.items():
                req_total = sum(d["requests"] for d in by_day.values())
                req_today = by_day.get(today, {}).get("requests", 0)
                uniq_today = len(by_day.get(today, {}).get("uniques", ()))
                req_7d = sum(by_day.get(dk, {}).get("requests", 0) for dk in recent_days[-7:])
                last_ts = max((d["last_ts"] for d in by_day.values()), default=0.0)
                series = [{"day": dk,
                           "requests": by_day.get(dk, {}).get("requests", 0),
                           "uniques": len(by_day.get(dk, {}).get("uniques", ()))}
                          for dk in recent_days]
                apps.append({
                    "app": app, "requests_total": req_total,
                    "requests_today": req_today, "uniques_today": uniq_today,
                    "requests_7d": req_7d, "last_ts": last_ts, "series": series,
                })
                tot_req += req_total
                tot_today += req_today
                tot_uniq_today += uniq_today
            apps.sort(key=lambda a: (a["requests_today"], a["requests_total"]), reverse=True)
            return {
                "generated_at": time.time(),
                "totals": {"apps": len(apps), "requests_total": tot_req,
                           "requests_today": tot_today, "uniques_today": tot_uniq_today},
                "apps": apps,
                "days": recent_days,
            }

    # ── persistence ──────────────────────────────────────────────────────
    def to_snapshot(self) -> dict:
        with self._lock:
            return {"version": 1, "saved_at": time.time(), "stats": {
                app: {day: {"requests": d["requests"],
                            "uniques": sorted(d["uniques"]),
                            "statuses": dict(d["statuses"]),
                            "last_ts": d["last_ts"]}
                      for day, d in by_day.items()}
                for app, by_day in self._stats.items()}}

    def from_snapshot(self, snap: dict) -> None:
        with self._lock:
            self._stats = defaultdict(lambda: defaultdict(self._blank))
            for app, by_day in (snap.get("stats") or {}).items():
                for day, d in by_day.items():
                    rec = self._stats[app][day]
                    rec["requests"] = int(d.get("requests", 0))
                    rec["uniques"] = set(d.get("uniques", []))
                    rec["statuses"] = defaultdict(int, {k: int(v) for k, v in (d.get("statuses") or {}).items()})
                    rec["last_ts"] = float(d.get("last_ts", 0.0))
            self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False


STORE = _Store()


# ── Snapshot I/O (file or S3/COS) ────────────────────────────────────────
def _s3_client():
    import boto3  # type: ignore
    kw = {}
    if _S3_ENDPOINT:
        kw["endpoint_url"] = _S3_ENDPOINT
    return boto3.client("s3", **kw)


def _load_snapshot() -> None:
    try:
        if _S3_BUCKET:
            obj = _s3_client().get_object(Bucket=_S3_BUCKET, Key=_S3_KEY)
            snap = json.loads(obj["Body"].read())
        else:
            p = Path(_DB_PATH)
            if not p.exists():
                log.info("no snapshot at %s — starting fresh", _DB_PATH)
                return
            snap = json.loads(p.read_text())
        STORE.from_snapshot(snap)
        log.info("loaded usage snapshot (%d apps)", len(snap.get("stats", {})))
    except Exception as exc:  # noqa: BLE001
        log.warning("snapshot load failed (starting fresh): %s", exc)


def _save_snapshot() -> None:
    snap = STORE.to_snapshot()
    data = json.dumps(snap).encode()
    try:
        if _S3_BUCKET:
            _s3_client().put_object(Bucket=_S3_BUCKET, Key=_S3_KEY, Body=data,
                                    ContentType="application/json")
        else:
            tmp = Path(_DB_PATH).with_suffix(".tmp")
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(data)
            tmp.replace(_DB_PATH)
        STORE.mark_clean()
        log.info("usage snapshot saved (%s)", "S3" if _S3_BUCKET else _DB_PATH)
    except Exception as exc:  # noqa: BLE001
        log.warning("snapshot save failed: %s", exc)


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import asyncio
    import uvicorn

    app = FastAPI(title="Usage Collector", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup():
        _load_snapshot()

        async def _saver():
            while True:
                await asyncio.sleep(_SAVE_INTERVAL)
                if STORE.dirty:
                    _save_snapshot()
        asyncio.create_task(_saver())

    @app.on_event("shutdown")
    async def _shutdown():
        if STORE.dirty:
            _save_snapshot()

    @app.post("/track")
    async def track(request: Request):
        if _TOKEN and request.headers.get("x-usage-token", "") != _TOKEN:
            return JSONResponse(status_code=401, content={"ok": False, "error": "bad token"})
        try:
            ev = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse(status_code=400, content={"ok": False, "error": "bad json"})
        app_name = str(ev.get("app") or "unknown")[:64]
        visitor = str(ev.get("visitor") or "")[:64]
        try:
            status = int(ev.get("status") or 0)
        except (TypeError, ValueError):
            status = 0
        try:
            ts = float(ev.get("ts") or time.time())
        except (TypeError, ValueError):
            ts = time.time()
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        STORE.record(app_name, day, visitor, status, ts)
        return JSONResponse(status_code=202, content={"ok": True})

    def _dash_authed(request: Request) -> bool:
        return (not _DASH_TOKEN) or request.query_params.get("token", "") == _DASH_TOKEN

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if not _dash_authed(request):
            return HTMLResponse("<h3>Usage dashboard: append ?token=… to view.</h3>",
                                status_code=401)
        return HTMLResponse(_HTML)

    @app.get("/api/stats")
    async def api_stats(request: Request):
        if not _dash_authed(request):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return STORE.rollup()

    @app.get("/health")
    async def health():
        return {"ok": True}

    print(f"\n  Usage Collector  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="Usage Collector — cuga-apps dashboard")
    parser.add_argument("--port", type=int, default=28827)
    args = parser.parse_args()
    _web(args.port)


if __name__ == "__main__":
    main()
