"""
Usage Collector — cross-app usage dashboard for the cuga-apps.

Every app installs _usage.py, which fire-and-forgets a tiny ping per request to
this collector's POST /track. The collector aggregates those into per-app,
per-day counters and serves a single dashboard (GET /) answering the question
"are people actually using these apps?" — requests, unique visitors/day, and
last-seen, across every app.

It also records three extra event kinds on the same /track endpoint:
  • kind="call"      — an external/provider API call (tavily, alpha_vantage,
                       watsonx, …), counted per provider per day.
  • kind="mcp"       — an MCP tool invocation, counted per MCP server AND per
                       tool per day (e.g. server="web", tool="tavily_search").
                       Surfaced on the dashboard's "MCP servers & tools" tab.
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


# When this collector process started — distinct from the image build time, so
# you can tell a redeploy (new build) from a cold start of the same image.
_STARTED_AT = time.time()


def _build_info() -> dict:
    """Image build provenance, baked into the all-in-one image at build time via
    build-args (see build/Dockerfile). Empty fields ⇒ a 'dev build' with no
    stamp. Surfaced read-only on the internal stats dashboard's footer."""
    return {
        "build_time":      os.getenv("CUGA_BUILD_TIME", ""),
        "git_commit":      os.getenv("CUGA_GIT_COMMIT", ""),
        "git_sha":         os.getenv("CUGA_GIT_SHA", ""),
        "git_branch":      os.getenv("CUGA_GIT_BRANCH", ""),
        "git_subject":     os.getenv("CUGA_GIT_SUBJECT", ""),
        "git_commit_time": os.getenv("CUGA_GIT_COMMIT_TIME", ""),
        "started_at":      _STARTED_AT,
    }


# ── Time-window helpers ──────────────────────────────────────────────────
# The dashboard tables and downloads break every count into these fixed UTC
# windows. "total" is all-time. Windows are inclusive of today (e.g. "7d" is the
# last 7 days up to and including today). NOTE: visitor hashes are daily-salted,
# so a visitor on two different days is two different hashes — summing daily
# unique counts over a window is therefore exact (no cross-day double count).
WINDOW_KEYS = ["today", "yesterday", "7d", "14d", "1m", "3m", "total"]


def _window_ctx() -> tuple:
    """Build the day strings/sets that classify a day into windows. Computed
    once per rollup/report so every entity is bucketed against the same 'now'."""
    base = datetime.now(timezone.utc).date().toordinal()

    def dayset(n: int) -> set:
        return {datetime.fromordinal(base - i).strftime("%Y-%m-%d") for i in range(n)}

    today = datetime.fromordinal(base).strftime("%Y-%m-%d")
    yesterday = datetime.fromordinal(base - 1).strftime("%Y-%m-%d")
    return (today, yesterday, dayset(7), dayset(14), dayset(30), dayset(90))


def _windows_for(day: str, ctx: tuple) -> list:
    """Window keys a given day belongs to (always includes 'total')."""
    today, yesterday, w7, w14, w1m, w3m = ctx
    out = []
    if day == today:
        out.append("today")
    if day == yesterday:
        out.append("yesterday")
    if day in w7:
        out.append("7d")
    if day in w14:
        out.append("14d")
    if day in w1m:
        out.append("1m")
    if day in w3m:
        out.append("3m")
    out.append("total")
    return out


def _zero_windows() -> dict:
    return {k: 0 for k in WINDOW_KEYS}


# ── Aggregate store ──────────────────────────────────────────────────────
# stats[app][day] = {"requests": int, "uniques": set[str],
#                    "statuses": {code: int}, "last_ts": float}
class _Store:
    def __init__(self) -> None:
        self._stats: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(self._blank))
        # providers[day][provider] = {"calls": int, "errors": int, "last_ts": float}
        self._providers: dict[str, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {"calls": 0, "errors": 0, "last_ts": 0.0}))
        # err_codes[day][provider][code] = int — failure-reason breakdown
        # (429, 404, timeout, …). In-memory only (not persisted in the snapshot);
        # rebuilds from live traffic after a restart.
        self._err_codes: dict[str, dict[str, dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int)))
        # mcp[day][server][tool] = {"calls": int, "errors": int, "last_ts": float}
        # — MCP tool usage broken out per server and per tool (persisted).
        self._mcp: dict[str, dict[str, dict[str, dict]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: {"calls": 0, "errors": 0, "last_ts": 0.0})))
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
                    utt: str | None = None, code: str | None = None,
                    ts: float = 0.0) -> None:
        with self._lock:
            rec = self._providers[day][provider]
            if ok:
                rec["calls"] += n
            else:
                rec["errors"] += n
                self._err_codes[day][provider][code or "error"] += n
            rec["last_ts"] = max(rec.get("last_ts", 0.0), ts)
            # In-process LLM calls carry the utterance id — attribute them to it.
            if utt:
                item = self._utt_by_id.get(utt)
                if item is not None:
                    item["calls"][provider] = item["calls"].get(provider, 0) + n
            self._dirty = True

    def record_mcp(self, server: str, tool: str, day: str, ok: bool, n: int,
                   utt: str | None = None, ts: float = 0.0) -> None:
        with self._lock:
            rec = self._mcp[day][server][tool]
            if ok:
                rec["calls"] += n
            else:
                rec["errors"] += n
            rec["last_ts"] = max(rec.get("last_ts", 0.0), ts)
            # Attribute to the in-flight utterance (chips), keyed by server name
            # so an utterance shows which MCP servers it exercised.
            if utt:
                item = self._utt_by_id.get(utt)
                if item is not None:
                    item["calls"][server] = item["calls"].get(server, 0) + n
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

    def hydrate_recent(self, items: list[dict]) -> None:
        """Seed the live recent-utterance feed from archived text (COS/file) at
        startup, so the Utterances tab isn't empty after a redeploy/cold start.

        Archived items carry app/text/ts only (no id/calls — call attribution is
        live-only). We deliberately do NOT touch ``_utt_counts`` (those come from
        the durable snapshot) or ``_utt_buffer`` (don't re-archive what we just
        read). ``items`` must be oldest→newest; the deque keeps the newest
        ``_UTT_RECENT``. Call once at startup, before traffic arrives."""
        with self._lock:
            for it in items:
                self._utt_recent.append({"app": it.get("app") or "unknown",
                                         "text": it.get("text") or "",
                                         "ts": float(it.get("ts") or 0.0)})

    def rollup(self, days: int = 14) -> dict:
        """Per-app summary + a daily series for the last `days` days."""
        with self._lock:
            today = _today()
            ctx = _window_ctx()
            recent = [(datetime.now(timezone.utc).date().toordinal() - i) for i in range(days)]
            recent_days = [datetime.fromordinal(o).strftime("%Y-%m-%d") for o in sorted(recent)]
            apps = []
            tot_req = tot_today = tot_uniq_today = 0
            tot_uniq_all = 0
            for app, by_day in self._stats.items():
                req_w = _zero_windows()       # requests per window
                uniq_w = _zero_windows()      # unique visitors per window (daily sum)
                last_ts = 0.0
                for dk, d in by_day.items():
                    nreq, nuniq = d["requests"], len(d["uniques"])
                    for w in _windows_for(dk, ctx):
                        req_w[w] += nreq
                        uniq_w[w] += nuniq
                    last_ts = max(last_ts, d["last_ts"])
                series = [{"day": dk,
                           "requests": by_day.get(dk, {}).get("requests", 0),
                           "uniques": len(by_day.get(dk, {}).get("uniques", ()))}
                          for dk in recent_days]
                row = {"app": app, "last_ts": last_ts, "series": series}
                for w in WINDOW_KEYS:
                    row[f"requests_{w}"] = req_w[w]
                    row[f"uniques_{w}"] = uniq_w[w]
                apps.append(row)
                tot_req += req_w["total"]
                tot_today += req_w["today"]
                tot_uniq_today += uniq_w["today"]
                tot_uniq_all += uniq_w["total"]
            apps.sort(key=lambda a: (a["requests_today"], a["requests_total"]), reverse=True)

            # Provider API calls — per-provider windowed call/error counts, last
            # seen, plus the failure-reason breakdown (how often a 429 was hit).
            provs: dict[str, dict] = {}

            def _prov(prov):
                return provs.setdefault(prov, {
                    "provider": prov, "calls": _zero_windows(), "errors": _zero_windows(),
                    "errors_by_code": defaultdict(int), "last_ts": 0.0})

            for day, by_prov in self._providers.items():
                wins = _windows_for(day, ctx)
                for prov, c in by_prov.items():
                    agg = _prov(prov)
                    for w in wins:
                        agg["calls"][w] += c["calls"]
                        agg["errors"][w] += c["errors"]
                    agg["last_ts"] = max(agg["last_ts"], c.get("last_ts", 0.0))
            for day, by_prov in self._err_codes.items():
                for prov, codes in by_prov.items():
                    agg = _prov(prov)
                    for code, k in codes.items():
                        agg["errors_by_code"][code] += k
            providers = []
            for agg in provs.values():
                flat = {"provider": agg["provider"], "last_ts": agg["last_ts"],
                        "errors_by_code": dict(agg["errors_by_code"])}
                for w in WINDOW_KEYS:
                    flat[f"calls_{w}"] = agg["calls"][w]
                    flat[f"errors_{w}"] = agg["errors"][w]
                providers.append(flat)
            providers.sort(key=lambda p: (p["calls_today"], p["calls_total"]), reverse=True)

            # Aggregate daily series for the charts (last `days` days):
            #  • api_calls — provider calls + errors per day (across all providers)
            #  • visits    — requests + unique visitors per day (across all apps)
            series_api = []
            for dk in recent_days:
                by_prov = self._providers.get(dk, {})
                series_api.append({
                    "day": dk,
                    "calls":  sum(c["calls"] for c in by_prov.values()),
                    "errors": sum(c["errors"] for c in by_prov.values()),
                })
            series_visits = []
            for dk in recent_days:
                day_req = sum(by_day.get(dk, {}).get("requests", 0)
                              for by_day in self._stats.values())
                day_uniq: set = set()
                for by_day in self._stats.values():
                    day_uniq |= by_day.get(dk, {}).get("uniques", set())
                series_visits.append({"day": dk, "requests": day_req, "uniques": len(day_uniq)})

            # MCP servers & tools — per-server totals + a per-day series, each
            # with its tools broken out the same way. This powers the dedicated
            # "MCP servers & tools" tab: a server's daily status up top, the
            # tools inside it further down.
            recent_set = set(recent_days)
            srv_acc: dict[str, dict] = {}

            def _srv(srv):
                return srv_acc.setdefault(srv, {
                    "server": srv, "calls": _zero_windows(), "errors": _zero_windows(),
                    "last_ts": 0.0,
                    "series": {d: {"calls": 0, "errors": 0} for d in recent_days},
                    "tools": {}})

            def _tool(s, tool):
                return s["tools"].setdefault(tool, {
                    "tool": tool, "calls": _zero_windows(), "errors": _zero_windows(),
                    "last_ts": 0.0,
                    "series": {d: {"calls": 0, "errors": 0} for d in recent_days}})

            for dk, by_srv in self._mcp.items():
                wins = _windows_for(dk, ctx)
                in_window = dk in recent_set
                for srv, by_tool in by_srv.items():
                    s = _srv(srv)
                    for tool, c in by_tool.items():
                        t = _tool(s, tool)
                        for w in wins:
                            s["calls"][w] += c["calls"]; s["errors"][w] += c["errors"]
                            t["calls"][w] += c["calls"]; t["errors"][w] += c["errors"]
                        lt = c.get("last_ts", 0.0)
                        s["last_ts"] = max(s["last_ts"], lt)
                        t["last_ts"] = max(t["last_ts"], lt)
                        if in_window:
                            s["series"][dk]["calls"] += c["calls"]; s["series"][dk]["errors"] += c["errors"]
                            t["series"][dk]["calls"] += c["calls"]; t["series"][dk]["errors"] += c["errors"]

            def _flat_mcp(node, key):
                flat = {key: node[key], "last_ts": node["last_ts"],
                        "series": [{"day": d, **node["series"][d]} for d in recent_days]}
                for w in WINDOW_KEYS:
                    flat[f"calls_{w}"] = node["calls"][w]
                    flat[f"errors_{w}"] = node["errors"][w]
                return flat

            mcp_servers = []
            for s in srv_acc.values():
                sflat = _flat_mcp(s, "server")
                tools = [_flat_mcp(t, "tool") for t in s["tools"].values()]
                tools.sort(key=lambda x: (x["calls_today"], x["calls_total"]), reverse=True)
                sflat["tools"] = tools
                mcp_servers.append(sflat)
            mcp_servers.sort(key=lambda s: (s["calls_today"], s["calls_total"]), reverse=True)
            mcp_series = []
            for dk in recent_days:
                by_srv = self._mcp.get(dk, {})
                mcp_series.append({
                    "day": dk,
                    "calls":  sum(c["calls"] for bt in by_srv.values() for c in bt.values()),
                    "errors": sum(c["errors"] for bt in by_srv.values() for c in bt.values()),
                })
            mcp_calls_today = sum(s["calls_today"] for s in mcp_servers)
            mcp_calls_total = sum(s["calls_total"] for s in mcp_servers)

            # Utterance counts per window (text isn't kept beyond the recent deque).
            utt_w = _zero_windows()
            for by_day in self._utt_counts.values():
                for dk, n in by_day.items():
                    for w in _windows_for(dk, ctx):
                        utt_w[w] += int(n)
            utt_today, utt_total = utt_w["today"], utt_w["total"]
            # newest first; copy the mutable `calls` dict under the lock so it
            # can't be mutated by a concurrent record_call during serialization.
            # Send the whole recent deque (each carries `ts`) so the UI can filter
            # the visible list by time window client-side.
            recent_utts = [
                {"app": u["app"], "text": u["text"], "ts": u["ts"],
                 **({"id": u["id"]} if u.get("id") else {}),
                 **({"calls": dict(u["calls"])} if u.get("calls") else {})}
                for u in list(self._utt_recent)[::-1]
            ]

            return {
                "generated_at": time.time(),
                "totals": {"apps": len(apps), "requests_total": tot_req,
                           "requests_today": tot_today, "uniques_today": tot_uniq_today,
                           "uniques_total": tot_uniq_all,
                           "calls_today": sum(p["calls_today"] for p in providers),
                           "mcp_calls_today": mcp_calls_today,
                           "mcp_calls_total": mcp_calls_total,
                           "utterances_total": utt_total, "utterances_today": utt_today},
                "apps": apps,
                "providers": providers,
                "mcp": {"servers": mcp_servers, "series": mcp_series},
                "utterances": {"total": utt_total, "today": utt_today,
                               "windows": utt_w, "recent": recent_utts},
                "series": {"api_calls": series_api, "visits": series_visits,
                           "mcp_calls": mcp_series},
                "days": recent_days,
            }

    def report(self, granularity: str = "daily") -> dict:
        """Per-period usage rollup for download. ``granularity`` is 'daily'
        (per YYYY-MM-DD) or 'monthly' (per YYYY-MM). Rolls up the same per-day
        aggregates the dashboard uses into downloadable rows: per-app usage,
        per-provider API calls, and a per-period total (unique visitors are a
        true union across days/apps, never a sum)."""
        monthly = str(granularity).lower().startswith("month")

        def bucket(day: str) -> str:
            return day[:7] if monthly else day          # YYYY-MM vs YYYY-MM-DD

        with self._lock:
            app_rows: dict = defaultdict(lambda: defaultdict(
                lambda: {"requests": 0, "uniques": set(), "utterances": 0}))
            period_uniq: dict = defaultdict(set)
            for app, by_day in self._stats.items():
                for day, d in by_day.items():
                    p = bucket(day)
                    r = app_rows[p][app]
                    r["requests"] += d["requests"]
                    r["uniques"] |= d["uniques"]
                    period_uniq[p] |= d["uniques"]
            for app, by_day in self._utt_counts.items():
                for day, n in by_day.items():
                    app_rows[bucket(day)][app]["utterances"] += int(n)
            prov_rows: dict = defaultdict(lambda: defaultdict(
                lambda: {"calls": 0, "errors": 0}))
            for day, by_prov in self._providers.items():
                p = bucket(day)
                for prov, c in by_prov.items():
                    prov_rows[p][prov]["calls"] += c["calls"]
                    prov_rows[p][prov]["errors"] += c["errors"]
            # MCP tool usage rolled up per period, keyed by "server/tool".
            mcp_rows: dict = defaultdict(lambda: defaultdict(
                lambda: {"calls": 0, "errors": 0}))
            for day, by_srv in self._mcp.items():
                p = bucket(day)
                for srv, by_tool in by_srv.items():
                    for tool, c in by_tool.items():
                        m = mcp_rows[p][f"{srv}/{tool}"]
                        m["calls"] += c["calls"]
                        m["errors"] += c["errors"]

            periods = sorted(set(app_rows) | set(prov_rows) | set(mcp_rows))
            apps_out, providers_out, mcp_out, totals_out = [], [], [], []
            for p in periods:
                t_req = t_utt = 0
                for app in sorted(app_rows.get(p, {})):
                    r = app_rows[p][app]
                    apps_out.append({"period": p, "app": app,
                                     "requests": r["requests"],
                                     "unique_visitors": len(r["uniques"]),
                                     "utterances": r["utterances"]})
                    t_req += r["requests"]
                    t_utt += r["utterances"]
                for prov in sorted(prov_rows.get(p, {})):
                    c = prov_rows[p][prov]
                    providers_out.append({"period": p, "provider": prov,
                                          "calls": c["calls"], "errors": c["errors"]})
                for st in sorted(mcp_rows.get(p, {})):
                    c = mcp_rows[p][st]
                    srv, _, tool = st.partition("/")
                    mcp_out.append({"period": p, "server": srv, "tool": tool,
                                    "calls": c["calls"], "errors": c["errors"]})
                totals_out.append({
                    "period": p, "requests": t_req,
                    "unique_visitors": len(period_uniq.get(p, set())),
                    "utterances": t_utt,
                    "provider_calls": sum(c["calls"] for c in prov_rows.get(p, {}).values()),
                    "provider_errors": sum(c["errors"] for c in prov_rows.get(p, {}).values()),
                    "mcp_calls": sum(c["calls"] for c in mcp_rows.get(p, {}).values()),
                    "mcp_errors": sum(c["errors"] for c in mcp_rows.get(p, {}).values()),
                })

            # ── Windowed summary (today / yesterday / 7d / 14d / 1m / 3m / total
            # + last seen) — the same numbers the dashboard tables show, so a
            # download is self-contained. Independent of the daily/monthly axis.
            windows = self._window_summary()
            return {"granularity": "monthly" if monthly else "daily",
                    "generated_at": time.time(),
                    "window_keys": WINDOW_KEYS,
                    "totals": totals_out, "apps": apps_out,
                    "providers": providers_out, "mcp": mcp_out,
                    "windows": windows}

    def _window_summary(self) -> dict:
        """Windowed counts (WINDOW_KEYS) + last-seen for every app, provider, and
        MCP server/tool, plus per-window totals and utterance counts. Assumes the
        caller already holds ``self._lock``."""
        ctx = _window_ctx()

        def accum(store, key_fn):
            agg: dict = {}
            for name, by_day in store.items():
                for dk, val in by_day.items():
                    wins = _windows_for(dk, ctx)
                    rec = agg.setdefault(name, {"w": _zero_windows(), "last_ts": 0.0,
                                                "extra": _zero_windows()})
                    n, e, ts = key_fn(val)
                    for w in wins:
                        rec["w"][w] += n
                        rec["extra"][w] += e
                    rec["last_ts"] = max(rec["last_ts"], ts)
            return agg

        # Apps: requests (+ unique visitors as the "extra" series, summed daily).
        app_agg = accum(self._stats,
                        lambda d: (d["requests"], len(d["uniques"]), d["last_ts"]))
        # Utterances per app per window (no last_ts dimension).
        utt_app: dict = {}
        for app, by_day in self._utt_counts.items():
            for dk, n in by_day.items():
                rec = utt_app.setdefault(app, _zero_windows())
                for w in _windows_for(dk, ctx):
                    rec[w] += int(n)
        apps_w = []
        for app in sorted(set(app_agg) | set(utt_app)):
            a = app_agg.get(app, {"w": _zero_windows(), "extra": _zero_windows(), "last_ts": 0.0})
            u = utt_app.get(app, _zero_windows())
            for w in WINDOW_KEYS:
                apps_w.append({"window": w, "app": app,
                               "requests": a["w"][w], "unique_visitors": a["extra"][w],
                               "utterances": u[w],
                               "last_seen": a["last_ts"] if w == "total" else ""})

        prov_agg = accum(self._providers,
                         lambda c: (c["calls"], c["errors"], c.get("last_ts", 0.0)))
        providers_w = []
        for prov in sorted(prov_agg):
            a = prov_agg[prov]
            for w in WINDOW_KEYS:
                providers_w.append({"window": w, "provider": prov,
                                    "calls": a["w"][w], "errors": a["extra"][w],
                                    "last_seen": a["last_ts"] if w == "total" else ""})

        # MCP keyed by "server/tool" so it flows through the same accum() shape.
        mcp_flat: dict = defaultdict(lambda: defaultdict(
            lambda: {"calls": 0, "errors": 0, "last_ts": 0.0}))
        for dk, by_srv in self._mcp.items():
            for srv, by_tool in by_srv.items():
                for tool, c in by_tool.items():
                    m = mcp_flat[dk][f"{srv}/{tool}"]
                    m["calls"] += c["calls"]; m["errors"] += c["errors"]
                    m["last_ts"] = max(m["last_ts"], c.get("last_ts", 0.0))
        mcp_agg = accum(mcp_flat,
                        lambda c: (c["calls"], c["errors"], c["last_ts"]))
        mcp_w = []
        for st in sorted(mcp_agg):
            a = mcp_agg[st]
            srv, _, tool = st.partition("/")
            for w in WINDOW_KEYS:
                mcp_w.append({"window": w, "server": srv, "tool": tool,
                              "calls": a["w"][w], "errors": a["extra"][w],
                              "last_seen": a["last_ts"] if w == "total" else ""})

        # Per-window totals across everything.
        totals_w = []
        for w in WINDOW_KEYS:
            totals_w.append({
                "window": w,
                "requests": sum(a["w"][w] for a in app_agg.values()),
                "unique_visitors": sum(a["extra"][w] for a in app_agg.values()),
                "utterances": sum(u[w] for u in utt_app.values()),
                "provider_calls": sum(a["w"][w] for a in prov_agg.values()),
                "provider_errors": sum(a["extra"][w] for a in prov_agg.values()),
                "mcp_calls": sum(a["w"][w] for a in mcp_agg.values()),
                "mcp_errors": sum(a["extra"][w] for a in mcp_agg.values()),
            })
        return {"totals": totals_w, "apps": apps_w,
                "providers": providers_w, "mcp": mcp_w}

    # ── persistence ──────────────────────────────────────────────────────
    # The snapshot carries the bounded, anonymous aggregates (requests, uniques,
    # provider call counts, utterance *counts*). Utterance *text* is NOT here —
    # it streams to the utterances/ prefix as append-only batches.
    def to_snapshot(self) -> dict:
        with self._lock:
            return {"version": 3, "saved_at": time.time(),
                    "stats": {
                        app: {day: {"requests": d["requests"],
                                    "uniques": sorted(d["uniques"]),
                                    "statuses": dict(d["statuses"]),
                                    "last_ts": d["last_ts"]}
                              for day, d in by_day.items()}
                        for app, by_day in self._stats.items()},
                    "providers": {day: {p: dict(c) for p, c in by_prov.items()}
                                  for day, by_prov in self._providers.items()},
                    "mcp": {day: {srv: {tool: dict(c) for tool, c in by_tool.items()}
                                  for srv, by_tool in by_srv.items()}
                            for day, by_srv in self._mcp.items()},
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
            self._providers = defaultdict(lambda: defaultdict(lambda: {"calls": 0, "errors": 0, "last_ts": 0.0}))
            for day, by_prov in (snap.get("providers") or {}).items():
                for prov, c in by_prov.items():
                    self._providers[day][prov] = {"calls": int(c.get("calls", 0)),
                                                  "errors": int(c.get("errors", 0)),
                                                  "last_ts": float(c.get("last_ts", 0.0))}
            self._mcp = defaultdict(
                lambda: defaultdict(lambda: defaultdict(lambda: {"calls": 0, "errors": 0, "last_ts": 0.0})))
            for day, by_srv in (snap.get("mcp") or {}).items():
                for srv, by_tool in by_srv.items():
                    for tool, c in by_tool.items():
                        self._mcp[day][srv][tool] = {"calls": int(c.get("calls", 0)),
                                                     "errors": int(c.get("errors", 0)),
                                                     "last_ts": float(c.get("last_ts", 0.0))}
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


# ── Recent-utterance hydration (read archived text back at startup) ───────
# The aggregate snapshot restores utterance *counts* but not the recent *text*
# feed (text lives append-only under <prefix>/<day>/*.jsonl). After a cold start
# the Utterances tab would otherwise be empty while counts show hundreds, so on
# startup we read just enough of the newest batches to refill the live feed.
def _batch_item_count(key: str) -> int:
    """Items in a batch, parsed from its '<ms>-<count>.jsonl' name (0 if odd)."""
    name = key.rsplit("/", 1)[-1]
    try:
        return int(name.rsplit("-", 1)[1].split(".")[0])
    except Exception:  # noqa: BLE001
        return 0


def _list_utt_batches() -> list[str]:
    """All utterance batch keys/paths, sorted oldest→newest. The keys embed the
    day and a millisecond stamp, so lexicographic sort ≈ chronological."""
    prefix = _UTT_PREFIX.rstrip("/") + "/"
    if _S3_BUCKET:
        keys: list[str] = []
        client = _s3_client()
        token = None
        while True:
            kw = {"Bucket": _S3_BUCKET, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            resp = client.list_objects_v2(**kw)
            keys.extend(o["Key"] for o in resp.get("Contents", [])
                        if o.get("Key", "").endswith(".jsonl"))
            if resp.get("IsTruncated"):
                token = resp.get("NextContinuationToken")
            else:
                break
        return sorted(keys)
    base = Path(_DB_PATH).parent / _UTT_PREFIX
    if not base.exists():
        return []
    files = [p for p in base.glob("*/*.jsonl")]
    files.sort(key=lambda p: (p.parent.name, p.name))
    return [str(p) for p in files]


def _read_utt_batch(key: str) -> list[dict]:
    try:
        if _S3_BUCKET:
            body = _s3_client().get_object(Bucket=_S3_BUCKET, Key=key)["Body"].read().decode("utf-8", "replace")
        else:
            body = Path(key).read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if d.get("text"):
            out.append({"app": d.get("app") or "unknown", "text": d["text"],
                        "ts": float(d.get("ts") or 0.0)})
    return out


def _hydrate_recent() -> None:
    """Refill STORE's recent-utterance feed from the archive (newest first), so
    the Utterances tab is populated after a cold start. Reads only enough of the
    newest batches to reach _UTT_RECENT items. Best-effort; never raises."""
    try:
        batches = _list_utt_batches()          # oldest→newest
        if not batches:
            return
        collected: list[dict] = []
        for key in reversed(batches):          # newest first, walk back
            collected.extend(_read_utt_batch(key))
            if len(collected) >= _UTT_RECENT:
                break
        if not collected:
            return
        collected.sort(key=lambda d: d["ts"])  # chronological (oldest→newest)
        STORE.hydrate_recent(collected[-_UTT_RECENT:])
        log.info("hydrated %d recent utterance(s) from %s",
                 min(len(collected), _UTT_RECENT), "S3" if _S3_BUCKET else "file")
    except Exception as exc:  # noqa: BLE001
        log.warning("recent-utterance hydrate skipped: %s", exc)


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import asyncio
    import uvicorn

    app = FastAPI(title="Usage Collector", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup():
        _load_snapshot()
        _hydrate_recent()   # refill the recent-utterance feed from the archive

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
                              utt=(str(ev.get("utt"))[:32] if ev.get("utt") else None),
                              code=(str(ev.get("code"))[:24] if ev.get("code") else None),
                              ts=ts)
        elif kind == "mcp":
            server = str(ev.get("server") or "unknown")[:40]
            tool = str(ev.get("tool") or "unknown")[:64]
            try:
                n = int(ev.get("n") or 1)
            except (TypeError, ValueError):
                n = 1
            STORE.record_mcp(server, tool, day, bool(ev.get("ok", True)), n,
                             utt=(str(ev.get("utt"))[:32] if ev.get("utt") else None),
                             ts=ts)
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

    @app.get("/api/build")
    async def api_build(request: Request):
        """Image build provenance (git commit + build time) for the dashboard
        footer, so you can tell which build is live. Token-gated like the rest."""
        if not _dash_authed(request):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return _build_info()

    @app.get("/api/report")
    async def api_report(request: Request, granularity: str = "daily",
                         format: str = "csv"):
        """Download a usage report. ?granularity=daily|monthly · ?format=csv|json
        Token-gated like the dashboard (?token=…). CSV opens straight in Excel.
        Two row groups: the per-period breakdown (section TOTAL/APP/PROVIDER/MCP,
        the ``period`` column holds a date) and the windowed summary the dashboard
        tables show (section WIN-*, the ``period`` column holds a window name like
        today / yesterday / 7d / 14d / 1m / 3m / total)."""
        if not _dash_authed(request):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        g = "monthly" if str(granularity).lower().startswith("month") else "daily"
        rep = STORE.report(g)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        fname = f"cuga_usage_{g}_{stamp}"
        if str(format).lower() == "json":
            return JSONResponse(rep, headers={
                "Content-Disposition": f'attachment; filename="{fname}.json"'})
        import csv
        import io
        from fastapi.responses import Response

        def _iso(ts) -> str:
            if not ts:
                return ""
            try:
                return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
            except Exception:  # noqa: BLE001
                return ""

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["section", "period", "name", "requests",
                    "unique_visitors", "utterances", "calls", "errors", "last_seen"])
        for r in rep["totals"]:
            w.writerow(["TOTAL", r["period"], "(all apps)", r["requests"],
                        r["unique_visitors"], r["utterances"],
                        r["provider_calls"] + r.get("mcp_calls", 0),
                        r["provider_errors"] + r.get("mcp_errors", 0), ""])
        for r in rep["apps"]:
            w.writerow(["APP", r["period"], r["app"], r["requests"],
                        r["unique_visitors"], r["utterances"], "", "", ""])
        for r in rep["providers"]:
            w.writerow(["PROVIDER", r["period"], r["provider"], "", "", "",
                        r["calls"], r["errors"], ""])
        for r in rep.get("mcp", []):
            w.writerow(["MCP", r["period"], r["server"] + "/" + r["tool"], "", "", "",
                        r["calls"], r["errors"], ""])
        # Windowed summary rows (today / yesterday / 7d / 14d / 1m / 3m / total).
        win = rep.get("windows", {})
        for r in win.get("totals", []):
            w.writerow(["WIN-TOTAL", r["window"], "(all apps)", r["requests"],
                        r["unique_visitors"], r["utterances"],
                        r["provider_calls"] + r.get("mcp_calls", 0),
                        r["provider_errors"] + r.get("mcp_errors", 0), ""])
        for r in win.get("apps", []):
            w.writerow(["WIN-APP", r["window"], r["app"], r["requests"],
                        r["unique_visitors"], r["utterances"], "", "", _iso(r.get("last_seen"))])
        for r in win.get("providers", []):
            w.writerow(["WIN-PROVIDER", r["window"], r["provider"], "", "", "",
                        r["calls"], r["errors"], _iso(r.get("last_seen"))])
        for r in win.get("mcp", []):
            w.writerow(["WIN-MCP", r["window"], r["server"] + "/" + r["tool"], "", "", "",
                        r["calls"], r["errors"], _iso(r.get("last_seen"))])
        return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'})

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
