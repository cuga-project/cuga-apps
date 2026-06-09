"""
Usage Collector — cross-app usage dashboard for the cuga-apps.

Every app installs _usage.py, which fire-and-forgets a tiny ping per request to
this collector's POST /track. The collector aggregates those into per-app,
per-day counters and serves a single dashboard (GET /) answering the question
"are people actually using these apps?" — requests, unique visitors/day, and
last-seen, across every app.

It also records two extra event kinds on the same /track endpoint:
  • kind="call"      — an external/provider API call (tavily, alpha_vantage,
                       watsonx, …), counted per provider per day.
  • kind="utterance" — a user's natural-language input. Counts go in the
                       snapshot; the *text* streams to the utterances/ prefix as
                       append-only daily batches (so a COS lifecycle rule can
                       expire it — see build/DEPLOYMENT.md).

Bucket layout (when USAGE_S3_BUCKET is set):
  rollup/usage_db.json          aggregate snapshot (set USAGE_S3_KEY to this)
  utterances/<day>/<batch>.jsonl  append-only utterance text

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
from collections import defaultdict, deque
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
# Utterances: how many recent ones to keep for the live dashboard, and where the
# append-only text batches land (S3 prefix or, in file mode, a local dir).
_UTT_RECENT = int(os.getenv("USAGE_UTTERANCE_RECENT", "200"))
_UTT_PREFIX = os.getenv("USAGE_UTTERANCE_PREFIX", "utterances")
_UTT_TEXT_MAX = int(os.getenv("USAGE_UTTERANCE_MAXLEN", "2000"))


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Aggregate store ──────────────────────────────────────────────────────
# stats[app][day] = {"requests": int, "uniques": set[str],
#                    "statuses": {code: int}, "last_ts": float}
class _Store:
    def __init__(self) -> None:
        self._stats: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(self._blank))
        # providers[day][provider] = {"calls": int, "errors": int}
        self._providers: dict[str, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {"calls": 0, "errors": 0}))
        # utt_counts[app][day] = int  (persisted totals; text is NOT kept here)
        self._utt_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._utt_recent: deque = deque(maxlen=_UTT_RECENT)   # live view, in-memory
        # id -> recent item, so a later provider call can attribute to its
        # utterance. Bounded to the deque (evicted ids are dropped).
        self._utt_by_id: dict[str, dict] = {}
        self._utt_buffer: list[dict] = []                     # pending COS flush
        self._utt_seq = 0
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

    def record_call(self, provider: str, day: str, ok: bool, n: int,
                    utt: str | None = None) -> None:
        with self._lock:
            rec = self._providers[day][provider]
            if ok:
                rec["calls"] += n
            else:
                rec["errors"] += n
            # In-process LLM calls carry the utterance id — attribute them to it.
            if utt:
                item = self._utt_by_id.get(utt)
                if item is not None:
                    item["calls"][provider] = item["calls"].get(provider, 0) + n
            self._dirty = True

    def record_utterance(self, app: str, day: str, text: str, ts: float,
                         uid: str | None = None) -> None:
        with self._lock:
            self._utt_counts[app][day] += 1
            item: dict = {"app": app, "text": text, "ts": ts}
            if uid:
                item["id"] = uid
                item["calls"] = {}            # provider -> count, filled by record_call
                # Keep the id index bounded to the deque: if this append will
                # evict the oldest item, drop that id from the index first.
                if len(self._utt_recent) == self._utt_recent.maxlen and self._utt_recent:
                    old = self._utt_recent[0]
                    if old.get("id"):
                        self._utt_by_id.pop(old["id"], None)
                self._utt_by_id[uid] = item
            self._utt_recent.append(item)
            # COS buffer stays text-only (calls arrive later; not persisted here).
            self._utt_buffer.append({"app": app, "text": text, "ts": ts, "day": day})
            self._dirty = True

    def drain_utterances(self) -> list[dict]:
        """Atomically take the pending utterance batch for a COS/file flush."""
        with self._lock:
            if not self._utt_buffer:
                return []
            batch, self._utt_buffer = self._utt_buffer, []
            self._utt_seq += 1
            return batch

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

            # Provider API calls — per-provider today + all-time.
            provs: dict[str, dict] = {}
            for day, by_prov in self._providers.items():
                for prov, c in by_prov.items():
                    agg = provs.setdefault(prov, {"provider": prov, "calls_today": 0,
                                                  "calls_total": 0, "errors_total": 0})
                    agg["calls_total"] += c["calls"]
                    agg["errors_total"] += c["errors"]
                    if day == today:
                        agg["calls_today"] += c["calls"]
            providers = sorted(provs.values(),
                               key=lambda p: (p["calls_today"], p["calls_total"]), reverse=True)

            utt_today = sum(by_day.get(today, 0) for by_day in self._utt_counts.values())
            utt_total = sum(sum(by_day.values()) for by_day in self._utt_counts.values())
            # newest first; copy the mutable `calls` dict under the lock so it
            # can't be mutated by a concurrent record_call during serialization.
            recent_utts = [
                {"app": u["app"], "text": u["text"], "ts": u["ts"],
                 **({"id": u["id"]} if u.get("id") else {}),
                 **({"calls": dict(u["calls"])} if u.get("calls") else {})}
                for u in list(self._utt_recent)[-50:][::-1]
            ]

            return {
                "generated_at": time.time(),
                "totals": {"apps": len(apps), "requests_total": tot_req,
                           "requests_today": tot_today, "uniques_today": tot_uniq_today,
                           "calls_today": sum(p["calls_today"] for p in providers),
                           "utterances_total": utt_total, "utterances_today": utt_today},
                "apps": apps,
                "providers": providers,
                "utterances": {"total": utt_total, "today": utt_today, "recent": recent_utts},
                "days": recent_days,
            }

    # ── persistence ──────────────────────────────────────────────────────
    # The snapshot carries the bounded, anonymous aggregates (requests, uniques,
    # provider call counts, utterance *counts*). Utterance *text* is NOT here —
    # it streams to the utterances/ prefix as append-only batches.
    def to_snapshot(self) -> dict:
        with self._lock:
            return {"version": 2, "saved_at": time.time(),
                    "stats": {
                        app: {day: {"requests": d["requests"],
                                    "uniques": sorted(d["uniques"]),
                                    "statuses": dict(d["statuses"]),
                                    "last_ts": d["last_ts"]}
                              for day, d in by_day.items()}
                        for app, by_day in self._stats.items()},
                    "providers": {day: {p: dict(c) for p, c in by_prov.items()}
                                  for day, by_prov in self._providers.items()},
                    "utt_counts": {app: dict(by_day)
                                   for app, by_day in self._utt_counts.items()}}

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
            self._providers = defaultdict(lambda: defaultdict(lambda: {"calls": 0, "errors": 0}))
            for day, by_prov in (snap.get("providers") or {}).items():
                for prov, c in by_prov.items():
                    self._providers[day][prov] = {"calls": int(c.get("calls", 0)),
                                                  "errors": int(c.get("errors", 0))}
            self._utt_counts = defaultdict(lambda: defaultdict(int))
            for app, by_day in (snap.get("utt_counts") or {}).items():
                for day, n in by_day.items():
                    self._utt_counts[app][day] = int(n)
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


def _flush_utterances() -> None:
    """Write pending utterance text as a new append-only batch object.

    Never overwrites: each flush is a distinct key under <prefix>/<day>/, so a
    failed flush can't corrupt earlier data. Grouped by day so a COS lifecycle
    rule can expire whole days. No-op when there's nothing buffered.
    """
    batch = STORE.drain_utterances()
    if not batch:
        return
    # Group by day so each object lands under its day's prefix.
    by_day: dict[str, list[dict]] = defaultdict(list)
    for item in batch:
        by_day[item.get("day") or _today()].append(
            {"app": item["app"], "text": item["text"], "ts": item["ts"]})
    ms = int(time.time() * 1000)
    try:
        for day, items in by_day.items():
            body = ("\n".join(json.dumps(it) for it in items) + "\n").encode()
            if _S3_BUCKET:
                key = f"{_UTT_PREFIX}/{day}/{ms}-{len(items)}.jsonl"
                _s3_client().put_object(Bucket=_S3_BUCKET, Key=key, Body=body,
                                        ContentType="application/x-ndjson")
            else:
                d = Path(_DB_PATH).parent / _UTT_PREFIX / day
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{ms}-{len(items)}.jsonl").write_bytes(body)
        log.info("flushed %d utterance(s) (%s)", len(batch), "S3" if _S3_BUCKET else "file")
    except Exception as exc:  # noqa: BLE001
        log.warning("utterance flush failed (dropped %d): %s", len(batch), exc)


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
                _flush_utterances()
                if STORE.dirty:
                    _save_snapshot()
        asyncio.create_task(_saver())

    @app.on_event("shutdown")
    async def _shutdown():
        _flush_utterances()
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
        try:
            ts = float(ev.get("ts") or time.time())
        except (TypeError, ValueError):
            ts = time.time()
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        kind = ev.get("kind") or "request"

        if kind == "call":
            provider = str(ev.get("provider") or "unknown")[:40]
            try:
                n = int(ev.get("n") or 1)
            except (TypeError, ValueError):
                n = 1
            STORE.record_call(provider, day, bool(ev.get("ok", True)), n,
                              utt=(str(ev.get("utt"))[:32] if ev.get("utt") else None))
        elif kind == "utterance":
            text = str(ev.get("text") or "")[:_UTT_TEXT_MAX]
            if text:
                STORE.record_utterance(app_name, day, text, ts,
                                       uid=(str(ev.get("id"))[:32] if ev.get("id") else None))
        else:                                   # request (default / back-compat)
            visitor = str(ev.get("visitor") or "")[:64]
            try:
                status = int(ev.get("status") or 0)
            except (TypeError, ValueError):
                status = 0
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
