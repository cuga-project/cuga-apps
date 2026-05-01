"""
Server Monitor — web UI powered by CugaAgent + FastAPI
=======================================================

Starts a browser UI at http://127.0.0.1:28767 with:

  Live Metrics      — CPU / RAM / Disk / Load gauges, auto-refreshed
  Chat              — ask the agent anything about system health
  Alert Log         — background monitor logs threshold breaches + diagnoses
  Alert Settings    — configure poll interval, cooldown, and thresholds

Run:
    python main.py
    python main.py --port 9000
    python main.py --provider anthropic

No email integration — alerts are surfaced in the UI and server log only.

Prerequisites:
    pip install -r requirements.txt

Environment variables:
    LLM_PROVIDER    rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL       model override
    POLL_INTERVAL_SECONDS   metric poll frequency (default: 60)
    ALERT_COOLDOWN_SECONDS  min seconds between repeated alerts (default: 900)
    DISK_THRESHOLD  warn % (default: 80)   DISK_CRITICAL  crit % (default: 90)
    CPU_THRESHOLD   warn % (default: 75)   CPU_CRITICAL   crit % (default: 90)
    RAM_THRESHOLD   warn % (default: 80)   RAM_CRITICAL   crit % (default: 92)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistent store
# ---------------------------------------------------------------------------

_STORE_PATH = _DIR / ".store.json"

_DEFAULT_STORE = {
    "thresholds": {
        "cpu_warn":  float(os.getenv("CPU_THRESHOLD",  "75")),
        "cpu_crit":  float(os.getenv("CPU_CRITICAL",   "90")),
        "ram_warn":  float(os.getenv("RAM_THRESHOLD",  "80")),
        "ram_crit":  float(os.getenv("RAM_CRITICAL",   "92")),
        "disk_warn": float(os.getenv("DISK_THRESHOLD", "80")),
        "disk_crit": float(os.getenv("DISK_CRITICAL",  "90")),
    },
    "poll_interval_seconds": int(os.getenv("POLL_INTERVAL_SECONDS", "60")),
    "cooldown_seconds":      int(os.getenv("ALERT_COOLDOWN_SECONDS", "900")),
}


def _load_store() -> dict:
    try:
        if _STORE_PATH.exists():
            return json.loads(_STORE_PATH.read_text())
    except Exception as exc:
        log.warning("Could not read store: %s", exc)
    return {}


def _save_store(data: dict) -> None:
    try:
        _STORE_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        log.warning("Could not write store: %s", exc)


def _get_store() -> dict:
    """Return merged store: persisted values over defaults."""
    defaults = dict(_DEFAULT_STORE)
    stored   = _load_store()
    defaults["thresholds"] = {**defaults["thresholds"], **stored.get("thresholds", {})}
    if "poll_interval_seconds" in stored:
        defaults["poll_interval_seconds"] = stored["poll_interval_seconds"]
    if "cooldown_seconds" in stored:
        defaults["cooldown_seconds"] = stored["cooldown_seconds"]
    return defaults


def _update_store(**fields) -> None:
    data = _load_store()
    data.update(fields)
    _save_store(data)


# ---------------------------------------------------------------------------
# Agent tools (adapted from agent.py — no cuga++ runtime dependency)
# ---------------------------------------------------------------------------

def _make_tools():
    import json as _json
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools
    from metrics import (
        list_top_processes as _top_procs,
        check_disk_usage   as _disk_usage,
        find_large_files   as _large_files,
        get_service_status as _svc_status,
    )

    # get_system_metrics_with_alerts is on mcp-local. Reuse its severity +
    # alerts logic instead of duplicating it here. The other 4 metrics tools
    # below stay inline because their inline implementations are richer than
    # mcp-local's (du-based subdir breakdown, find-based large files,
    # allowlisted systemctl, allowlisted shell command).
    mcp_local_tools = load_tools(["local"])
    # Filter to just the alerts-aware metrics tool — we don't want the
    # simpler get_system_metrics or duplicates of our local versions
    # confusing the LLM's tool selection.
    mcp_local_tools = [t for t in mcp_local_tools if t.name == "get_system_metrics_with_alerts"]

    @tool
    def list_top_processes(by: str = "cpu", n: int = 10) -> str:
        """
        Return the top-N processes sorted by CPU or memory usage.

        Args:
            by: "cpu" (default) or "memory"
            n:  Number of processes to return (default 10)
        """
        return _json.dumps(_top_procs(by=by, n=n))

    @tool
    def check_disk_usage(path: str = "/") -> str:
        """
        Return disk usage of direct subdirectories under `path`.
        Use this when disk is high to identify which directory is the biggest.

        Args:
            path: Directory to inspect (default "/")
        """
        return _json.dumps(_disk_usage(path=path))

    @tool
    def find_large_files(path: str = "/", min_mb: int = 100, top_n: int = 20) -> str:
        """
        Find files larger than `min_mb` MB under `path`.
        Use this to identify specific large files when disk is high.

        Args:
            path:   Root path to search (default "/")
            min_mb: Minimum file size in MB (default 100)
            top_n:  Max results to return (default 20)
        """
        return _json.dumps(_large_files(path=path, min_mb=min_mb, top_n=top_n))

    @tool
    def get_service_status(service: str) -> str:
        """
        Return the status of a named system service via systemctl (Linux) or
        launchctl (macOS). Only services in the ALLOWED_SERVICES env var are checked.

        Args:
            service: Service name, e.g. "nginx", "postgres", "redis"
        """
        return _json.dumps(_svc_status(service=service))

    @tool
    def run_safe_command(cmd: str) -> str:
        """
        Run a read-only diagnostic shell command from the allowlist.

        Allowed commands: df -h, du -sh, uptime, free -h, ps aux,
        netstat -tlnp, iostat, vmstat, top -b / top -l

        Args:
            cmd: The exact shell command to run (no pipes, no semicolons)
        """
        import shlex, subprocess as _sp

        ALLOWED_PREFIXES = (
            "df ", "df\t", "df\n", "df",
            "du ",
            "uptime",
            "free",
            "ps ",
            "netstat",
            "iostat",
            "vmstat",
            "top -b",
            "top -l",
        )
        cmd = cmd.strip()
        if not any(cmd.startswith(p) for p in ALLOWED_PREFIXES):
            return _json.dumps({"error": f"Command not in allowlist: {cmd!r}"})
        for ch in (";", "&&", "||", "|", "`", "$", ">", "<", "\n"):
            if ch in cmd:
                return _json.dumps({"error": f"Shell metacharacter {ch!r} not allowed."})
        try:
            result = _sp.run(shlex.split(cmd), capture_output=True, text=True, timeout=10)
            return _json.dumps({
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:500],
                "returncode": result.returncode,
            })
        except Exception as exc:
            return _json.dumps({"error": str(exc)})

    return [
        *mcp_local_tools,            # get_system_metrics_with_alerts (mcp-local)
        list_top_processes,
        check_disk_usage,
        find_large_files,
        get_service_status,
        run_safe_command,
    ]


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Server Health Monitor

You are a senior DevOps engineer. You monitor system health, diagnose problems, and recommend or execute safe remediation steps.

## Tools available

| Tool | When to use |
|---|---|
| `get_system_metrics_with_alerts` | First call for any health check — gets CPU, RAM, disk, load average. Pass `thresholds` from this app's config (see below) so severity matches operator policy. |
| `list_top_processes` | When CPU or RAM is high — identifies the offending process(es) |
| `check_disk_usage` | When disk is high — shows which directories are largest |
| `find_large_files` | When disk is high — locates specific large files to review |
| `get_service_status` | When you suspect a service is down or misbehaving |
| `run_safe_command` | For safe read-only diagnostics (allowed list enforced by the tool) |

## Severity levels and configured thresholds

This deployment is configured with these thresholds — pass them as the
`thresholds` arg to `get_system_metrics_with_alerts` so the tool's severity
classification matches operator policy (defaults shown in parens):

  cpu_warn  = {cpu_warn}    (default 75)   cpu_crit  = {cpu_crit}    (default 90)
  ram_warn  = {ram_warn}    (default 80)   ram_crit  = {ram_crit}    (default 92)
  disk_warn = {disk_warn}    (default 80)   disk_crit = {disk_crit}    (default 90)

Severity ladder: ok / warning / critical.

## Reactive alert flow (triggered by background monitor)

When called because thresholds were exceeded:

1. Call `get_system_metrics_with_alerts` to get current readings.
2. For each alert in `metrics["alerts"]`:
   - **Disk high** → call `check_disk_usage("/")` to find the bloated directory, then `find_large_files("/var/log", min_mb=50)` or similar path.
   - **CPU high** → call `list_top_processes(by="cpu")` to identify the offender.
   - **RAM high** → call `list_top_processes(by="memory")` to identify the offender.
   - **Load high** → call `list_top_processes(by="cpu", n=5)` and `run_safe_command("uptime")`.
3. Compose a concise alert report (see format below).
4. Return only the report — the caller will store it in the alert log.

## Health briefing flow (requested by user in chat)

When the user asks for a health briefing or daily summary:

1. Call `get_system_metrics_with_alerts` for the current snapshot.
2. If any service names are known from context, call `get_service_status` for each.
3. Compose a health briefing (see format below).
4. Return only the briefing.

## Interactive queries

When the user asks a direct question:
- "what's using all the disk?" → `check_disk_usage` + `find_large_files`
- "why is the server slow?" → `get_system_metrics_with_alerts` + `list_top_processes(by="cpu")` + `run_safe_command("uptime")`
- "is nginx running?" → `get_service_status("nginx")`
- "show me memory usage" → `get_system_metrics_with_alerts` + `list_top_processes(by="memory")`

## Alert report format

```
🚨 Server Alert — {hostname} — {timestamp}

Severity: {CRITICAL|WARNING}

Metrics:
  CPU:  {cpu_pct}%  |  RAM: {ram_pct}%  |  Disk: {disk_pct}%
  Load: {load_1m} / {load_5m} / {load_15m}  (1m/5m/15m)
  Uptime: {uptime_fmt}

Alerts:
  • {alert 1}
  • {alert 2}

Diagnosis:
  {1–3 sentences: what is likely causing the issue}

Top offenders:
  {top 3–5 processes if relevant, with PID, name, usage}

Recommended action:
  {specific, safe steps — never suggest rm -rf or destructive ops}
  {if disk: "Review /var/log — largest files: X, Y, Z"}
  {if CPU: "PID {n} ({name}) consuming {pct}% — consider restarting if stuck"}
  {if RAM: "PID {n} ({name}) consuming {mb}MB — investigate for memory leak"}
```

## Morning briefing format

```
☀️ Morning Briefing — {hostname} — {date}

System Health: {OK ✅ | WARNING ⚠️ | CRITICAL 🚨}

  CPU:  {cpu_pct}%  |  RAM: {ram_pct}%  |  Disk: {disk_pct}%
  Uptime: {uptime_fmt}  |  Load: {load_1m}

Services:
  {service}: {active|stopped} {✅|❌}

Summary:
  {1–2 sentences describing overall health}
  {Note anything unusual or trending toward a threshold}
```

## Safety rules

- Never suggest or run destructive commands (rm, kill -9, DROP, truncate).
- Never recommend restarting a database without explicit user confirmation.
- Always prefer `df`, `du`, `ps`, `top`, `uptime`, `systemctl status` over anything that writes.
- If disk is high, suggest *reviewing* large files — never suggest deleting them autonomously.
- Report findings clearly and let the human decide on destructive actions.
- If a process looks stuck (high CPU, state=zombie), report it — don't kill it.
"""


def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm

    # Inline the configured thresholds into the prompt so the LLM passes them
    # to mcp-local's get_system_metrics_with_alerts. Use str.replace, not
    # str.format — the prompt contains other {placeholders} the LLM is meant
    # to fill at output time (hostname, timestamps, etc.).
    system_prompt = _SYSTEM
    for key, val in _DEFAULT_STORE["thresholds"].items():
        system_prompt = system_prompt.replace("{" + key + "}", str(val))

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=system_prompt,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Background monitor — polls metrics, fires agent on threshold breach
# ---------------------------------------------------------------------------

_alert_log: list[dict] = []   # in-memory, capped at 50
_last_alert_ts: float  = 0.0  # epoch seconds of last alert fired


async def _run_diagnosis(agent, metrics: dict) -> dict:
    """Ask agent to diagnose a threshold breach. Returns alert log entry."""
    import json as _json
    severity = metrics.get("severity", "warning")
    alerts   = metrics.get("alerts", [])

    prefix = "CRITICAL" if severity == "critical" else "WARNING"
    message = (
        f"{prefix} server health alert triggered. Current metrics:\n\n"
        f"{_json.dumps(metrics, indent=2)}\n\n"
        f"Diagnose the issues, identify top offenders (use list_top_processes "
        f"or check_disk_usage as needed), and compose a concise alert report."
    )
    thread = f"server-alert-{severity}"
    try:
        result = await agent.invoke(message, thread_id=thread)
        diagnosis = result.answer
    except Exception as exc:
        diagnosis = f"Error running diagnosis: {exc}"

    entry = {
        "id":        uuid.uuid4().hex[:8],
        "severity":  severity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alerts":    alerts,
        "metrics":   {k: metrics.get(k) for k in
                      ("cpu_pct", "ram_pct", "disk_pct", "load_avg_1m", "hostname")},
        "diagnosis": diagnosis,
    }
    _alert_log.insert(0, entry)
    if len(_alert_log) > 50:
        _alert_log.pop()

    log.info("[MONITOR] %s — %s", severity.upper(), ", ".join(alerts))
    return entry


async def _monitor_loop(agent) -> None:
    """Background task: poll metrics, fire agent diagnosis on threshold breach."""
    global _last_alert_ts
    from metrics import get_system_metrics, has_alerts

    while True:
        cfg          = _get_store()
        interval     = cfg.get("poll_interval_seconds", 60)
        cooldown     = cfg.get("cooldown_seconds", 900)
        thresholds   = cfg.get("thresholds", {})

        # Apply current thresholds to metrics module (env-var level)
        import metrics as _m
        _m.CPU_WARN_PCT  = thresholds.get("cpu_warn",  75)
        _m.CPU_CRIT_PCT  = thresholds.get("cpu_crit",  90)
        _m.RAM_WARN_PCT  = thresholds.get("ram_warn",  80)
        _m.RAM_CRIT_PCT  = thresholds.get("ram_crit",  92)
        _m.DISK_WARN_PCT = thresholds.get("disk_warn", 80)
        _m.DISK_CRIT_PCT = thresholds.get("disk_crit", 90)

        try:
            m = get_system_metrics()
            if has_alerts(m):
                now = datetime.now(timezone.utc).timestamp()
                if now - _last_alert_ts >= cooldown:
                    _last_alert_ts = now
                    asyncio.create_task(_run_diagnosis(agent, m))
        except Exception as exc:
            log.warning("Monitor poll error: %s", exc)

        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


class ThresholdsReq(BaseModel):
    cpu_warn:  float = 75
    cpu_crit:  float = 90
    ram_warn:  float = 80
    ram_crit:  float = 92
    disk_warn: float = 80
    disk_crit: float = 90


class PollSettingsReq(BaseModel):
    poll_interval_seconds: int = 60
    cooldown_seconds:      int = 900


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    agent = make_agent()

    app = FastAPI(title="Server Monitor")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # ── Startup: launch background monitor ──────────────────────────────────

    @app.on_event("startup")
    async def _startup():
        asyncio.create_task(_monitor_loop(agent))
        log.info("Background monitor started.")

    # ── API: live metrics ────────────────────────────────────────────────────

    @app.get("/metrics")
    async def api_metrics():
        from metrics import get_system_metrics
        return get_system_metrics()

    # ── API: chat ────────────────────────────────────────────────────────────

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            result = await agent.invoke(req.question, thread_id="chat")
            return {"answer": result.answer}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── API: alert log ───────────────────────────────────────────────────────

    @app.get("/alerts/log")
    async def api_alert_log():
        return _alert_log

    @app.post("/alerts/trigger")
    async def api_trigger():
        """Manually trigger a metrics check + diagnosis right now."""
        from metrics import get_system_metrics
        m = get_system_metrics()
        entry = await _run_diagnosis(agent, m)
        return entry

    # ── API: alert settings ──────────────────────────────────────────────────

    @app.get("/alerts/config")
    async def api_alert_config():
        return _get_store()

    @app.post("/alerts/thresholds")
    async def api_set_thresholds(req: ThresholdsReq):
        data = _load_store()
        data["thresholds"] = req.model_dump()
        _save_store(data)
        return {"ok": True}

    @app.post("/alerts/poll")
    async def api_set_poll(req: PollSettingsReq):
        data = _load_store()
        data["poll_interval_seconds"] = req.poll_interval_seconds
        data["cooldown_seconds"]      = req.cooldown_seconds
        _save_store(data)
        return {"ok": True}

    # ── HTML UI ──────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Server Monitor</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    min-height: 100vh;
  }

  /* ─── Header ─────────────────────────────────────────────────────── */
  header {
    background: #1a1a2e;
    border-bottom: 1px solid #2d2d4a;
    padding: 14px 28px;
    display: flex;
    align-items: center;
    gap: 16px;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  header h1 { font-size: 16px; font-weight: 700; color: #fff; letter-spacing: .3px; }
  header .hostname { font-size: 12px; color: #6b7280; margin-left: 4px; }
  header .badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .5px;
  }
  .badge.ok       { background: #14532d; color: #4ade80; }
  .badge.warning  { background: #713f12; color: #fbbf24; }
  .badge.critical { background: #7f1d1d; color: #f87171; }
  .badge.unknown  { background: #374151; color: #9ca3af; }
  .spacer { flex: 1; }
  .header-btn {
    padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
    cursor: pointer; border: 1px solid #374151; background: #1f2937; color: #d1d5db;
    transition: background .15s;
  }
  .header-btn:hover { background: #374151; }
  .last-updated { font-size: 11px; color: #4b5563; }

  /* ─── Layout ─────────────────────────────────────────────────────── */
  .layout {
    display: grid;
    grid-template-columns: 340px 1fr;
    gap: 20px;
    max-width: 1280px;
    margin: 0 auto;
    padding: 20px 24px;
  }

  /* ─── Cards ──────────────────────────────────────────────────────── */
  .card {
    background: #1a1a2e;
    border: 1px solid #2d2d4a;
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 16px;
  }
  .card-header {
    padding: 12px 16px 10px;
    border-bottom: 1px solid #2d2d4a;
    display: flex; align-items: center; gap: 8px;
  }
  .card-header h2 { font-size: 13px; font-weight: 600; color: #c5cae9; }
  .card-body { padding: 16px; }

  /* ─── Metric gauges ──────────────────────────────────────────────── */
  .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .metric-item { }
  .metric-label { font-size: 11px; color: #6b7280; margin-bottom: 4px; display: flex; justify-content: space-between; }
  .metric-val { font-weight: 600; color: #e2e8f0; }
  .gauge-bg {
    height: 6px; background: #2d2d4a; border-radius: 3px; overflow: hidden; margin-top: 2px;
  }
  .gauge-fill {
    height: 100%; border-radius: 3px; transition: width .5s ease, background .5s;
  }
  .gauge-ok       { background: #4ade80; }
  .gauge-warning  { background: #fbbf24; }
  .gauge-critical { background: #f87171; }
  .metric-sub { font-size: 10px; color: #4b5563; margin-top: 2px; }
  .alerts-list { margin-top: 12px; }
  .alert-chip {
    display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
    margin: 2px 2px 2px 0;
  }
  .chip-warning  { background: #451a03; color: #fbbf24; }
  .chip-critical { background: #450a0a; color: #f87171; }
  .chip-ok       { background: #052e16; color: #4ade80; }

  /* ─── Settings ───────────────────────────────────────────────────── */
  .settings-row {
    display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
  }
  .settings-row label { font-size: 12px; color: #9ca3af; width: 100px; flex-shrink: 0; }
  .settings-row input[type=number] {
    width: 70px; padding: 4px 8px; border-radius: 5px; font-size: 12px;
    background: #0f1117; border: 1px solid #374151; color: #e2e8f0;
    appearance: textfield;
  }
  .settings-hint { font-size: 10px; color: #4b5563; }
  .settings-section { font-size: 11px; font-weight: 600; color: #6b7280;
    text-transform: uppercase; letter-spacing: .5px; margin: 12px 0 6px; }
  .save-btn {
    padding: 5px 14px; border-radius: 6px; font-size: 12px; font-weight: 500;
    cursor: pointer; border: none; background: #2563eb; color: #fff;
    transition: background .15s; margin-top: 6px;
  }
  .save-btn:hover { background: #1d4ed8; }
  .save-btn:disabled { background: #374151; color: #6b7280; cursor: default; }
  .save-ok { color: #4ade80; font-size: 11px; margin-left: 8px; display: none; }

  /* ─── Right column ───────────────────────────────────────────────── */
  .right-col { }

  /* ─── Chat ───────────────────────────────────────────────────────── */
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .chip {
    padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 500;
    background: #1f2937; border: 1px solid #374151; color: #9ca3af;
    cursor: pointer; transition: all .15s;
  }
  .chip:hover { background: #2563eb; border-color: #2563eb; color: #fff; }
  .chat-input-row { display: flex; gap: 8px; }
  .chat-input {
    flex: 1; padding: 8px 12px; border-radius: 7px; font-size: 13px;
    background: #0f1117; border: 1px solid #374151; color: #e2e8f0;
    outline: none; transition: border-color .15s;
  }
  .chat-input:focus { border-color: #2563eb; }
  .chat-send {
    padding: 8px 16px; border-radius: 7px; font-size: 13px; font-weight: 500;
    cursor: pointer; border: none; background: #2563eb; color: #fff;
    transition: background .15s; white-space: nowrap;
  }
  .chat-send:hover { background: #1d4ed8; }
  .chat-send:disabled { background: #374151; color: #6b7280; cursor: default; }
  .chat-result {
    margin-top: 14px; padding: 14px; border-radius: 7px;
    background: #0f1117; border: 1px solid #2d2d4a;
    font-size: 13px; line-height: 1.6; color: #d1d5db;
    white-space: pre-wrap; min-height: 48px;
    display: none;
  }
  .chat-result.visible { display: block; }

  /* ─── Alert log ──────────────────────────────────────────────────── */
  .alert-entry {
    border: 1px solid #2d2d4a; border-radius: 7px; margin-bottom: 10px; overflow: hidden;
  }
  .alert-entry-header {
    padding: 10px 14px; display: flex; align-items: center; gap: 10px;
    cursor: pointer; user-select: none; transition: background .15s;
  }
  .alert-entry-header:hover { background: #1f2937; }
  .alert-sev {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    padding: 2px 7px; border-radius: 9px;
  }
  .sev-warning  { background: #451a03; color: #fbbf24; }
  .sev-critical { background: #450a0a; color: #f87171; }
  .sev-ok       { background: #052e16; color: #4ade80; }
  .alert-time { font-size: 11px; color: #6b7280; }
  .alert-chips-row { flex: 1; display: flex; flex-wrap: wrap; gap: 4px; }
  .alert-metrics-mini { font-size: 11px; color: #9ca3af; }
  .alert-expand { font-size: 11px; color: #4b5563; margin-left: auto; }
  .alert-body {
    padding: 12px 14px; font-size: 12px; line-height: 1.6; color: #d1d5db;
    white-space: pre-wrap; background: #0f1117; border-top: 1px solid #2d2d4a;
    display: none;
  }
  .alert-body.open { display: block; }
  .empty-log { font-size: 13px; color: #4b5563; text-align: center; padding: 24px; }
  .trigger-btn {
    padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
    cursor: pointer; border: 1px solid #374151; background: #1f2937; color: #d1d5db;
    transition: background .15s; margin-left: auto;
  }
  .trigger-btn:hover { background: #374151; }
  .trigger-btn:disabled { color: #4b5563; cursor: default; }
</style>
</head>
<body>

<!-- ─── Header ──────────────────────────────────────────────────────── -->
<header>
  <h1>⚡ Server Monitor</h1>
  <span class="hostname" id="hostname">—</span>
  <span class="badge unknown" id="sev-badge">—</span>
  <div class="spacer"></div>
  <span class="last-updated" id="last-updated"></span>
  <button class="header-btn" onclick="refreshMetrics()">↺ Refresh</button>
</header>

<!-- ─── Layout ──────────────────────────────────────────────────────── -->
<div class="layout">

  <!-- ─── Left column ──────────────────────────────────────────────── -->
  <div class="left-col">

    <!-- Live Metrics -->
    <div class="card">
      <div class="card-header">
        <h2>📊 Live Metrics</h2>
        <label style="font-size:11px;color:#6b7280;margin-left:auto;display:flex;align-items:center;gap:5px;cursor:pointer;">
          <input type="checkbox" id="auto-refresh" checked onchange="toggleAutoRefresh(this.checked)">
          auto-refresh
        </label>
      </div>
      <div class="card-body">
        <div class="metric-grid" id="metric-grid">
          <!-- filled by JS -->
        </div>
        <div class="alerts-list" id="alerts-list"></div>
      </div>
    </div>

    <!-- Alert Settings -->
    <div class="card">
      <div class="card-header"><h2>⚙️ Alert Settings</h2></div>
      <div class="card-body">

        <div class="settings-section">Poll &amp; cooldown</div>
        <div class="settings-row">
          <label>Poll every</label>
          <input type="number" id="poll-interval" min="10" max="3600" value="60">
          <span class="settings-hint">seconds</span>
        </div>
        <div class="settings-row">
          <label>Cooldown</label>
          <input type="number" id="cooldown" min="60" max="86400" value="900">
          <span class="settings-hint">seconds between alerts</span>
        </div>

        <div class="settings-section">Thresholds — warn / critical</div>
        <div class="settings-row">
          <label>CPU %</label>
          <input type="number" id="cpu-warn" min="1" max="100" value="75">
          <span style="color:#4b5563;font-size:12px;">/</span>
          <input type="number" id="cpu-crit" min="1" max="100" value="90">
        </div>
        <div class="settings-row">
          <label>RAM %</label>
          <input type="number" id="ram-warn" min="1" max="100" value="80">
          <span style="color:#4b5563;font-size:12px;">/</span>
          <input type="number" id="ram-crit" min="1" max="100" value="92">
        </div>
        <div class="settings-row">
          <label>Disk %</label>
          <input type="number" id="disk-warn" min="1" max="100" value="80">
          <span style="color:#4b5563;font-size:12px;">/</span>
          <input type="number" id="disk-crit" min="1" max="100" value="90">
        </div>

        <button class="save-btn" id="save-btn" onclick="saveSettings()">Save settings</button>
        <span class="save-ok" id="save-ok">✓ Saved</span>
      </div>
    </div>

  </div><!-- /left-col -->

  <!-- ─── Right column ─────────────────────────────────────────────── -->
  <div class="right-col">

    <!-- Chat -->
    <div class="card">
      <div class="card-header"><h2>💬 Chat — Ask the Agent</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">What's the current server health?</span>
          <span class="chip" onclick="ask(this.textContent)">What's using the most CPU right now?</span>
          <span class="chip" onclick="ask(this.textContent)">What's consuming the most memory?</span>
          <span class="chip" onclick="ask(this.textContent)">How much disk space is left?</span>
          <span class="chip" onclick="ask(this.textContent)">What's eating my disk?</span>
          <span class="chip" onclick="ask(this.textContent)">Why is the server slow?</span>
          <span class="chip" onclick="ask(this.textContent)">Give me a full health briefing</span>
          <span class="chip" onclick="ask(this.textContent)">Show load average and uptime</span>
          <span class="chip" onclick="ask(this.textContent)">Any zombie processes?</span>
          <span class="chip" onclick="ask(this.textContent)">Is nginx running?</span>
          <span class="chip" onclick="ask(this.textContent)">Top 5 memory-hungry processes</span>
          <span class="chip" onclick="ask(this.textContent)">Find files larger than 500MB</span>
        </div>
        <div class="chat-input-row">
          <input class="chat-input" id="chat-input" type="text"
            placeholder="Ask anything about system health…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="chat-send" id="chat-send" onclick="ask()">Ask</button>
        </div>
        <div class="chat-result" id="chat-result"></div>
      </div>
    </div>

    <!-- Alert Log -->
    <div class="card">
      <div class="card-header">
        <h2>🔔 Alert Log</h2>
        <button class="trigger-btn" id="trigger-btn" onclick="triggerNow()">▶ Check now</button>
      </div>
      <div class="card-body" id="alert-log-body">
        <div class="empty-log">No alerts yet — monitor is running in background.</div>
      </div>
    </div>

  </div><!-- /right-col -->
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────
let _autoRefreshTimer = null;
let _autoRefresh      = true;
const AUTO_REFRESH_MS = 15000;

// ── Metrics ────────────────────────────────────────────────────────────
async function refreshMetrics() {
  try {
    const m = await fetch('/metrics').then(r => r.json());
    renderMetrics(m);
  } catch(e) {
    console.error('metrics error', e);
  }
}

function gauge(pct, warn, crit) {
  const cls = pct >= crit ? 'gauge-critical' : pct >= warn ? 'gauge-warning' : 'gauge-ok';
  return `<div class="gauge-bg"><div class="gauge-fill ${cls}" style="width:${Math.min(pct||0,100)}%"></div></div>`;
}

function renderMetrics(m) {
  // Header badge
  const sev = m.severity || 'unknown';
  const badge = document.getElementById('sev-badge');
  badge.className = 'badge ' + sev;
  badge.textContent = sev.toUpperCase();
  document.getElementById('hostname').textContent = m.hostname || '';
  document.getElementById('last-updated').textContent =
    'Updated ' + new Date().toLocaleTimeString();

  // Metric grid
  const cfg = _cachedConfig || {};
  const t = cfg.thresholds || {};
  const cpuWarn  = t.cpu_warn  || 75;  const cpuCrit  = t.cpu_crit  || 90;
  const ramWarn  = t.ram_warn  || 80;  const ramCrit  = t.ram_crit  || 92;
  const diskWarn = t.disk_warn || 80;  const diskCrit = t.disk_crit || 90;

  const cpuPct  = m.cpu_pct  ?? null;
  const ramPct  = m.ram_pct  ?? null;
  const diskPct = m.disk_pct ?? null;
  const load1   = m.load_avg_1m ?? null;

  function metricCard(label, pct, warn, crit, sub) {
    const valStr = pct != null ? pct.toFixed(1) + '%' : '—';
    return `<div class="metric-item">
      <div class="metric-label"><span>${label}</span><span class="metric-val">${valStr}</span></div>
      ${pct != null ? gauge(pct, warn, crit) : '<div class="gauge-bg"></div>'}
      <div class="metric-sub">${sub || ''}</div>
    </div>`;
  }

  const loadSub = load1 != null
    ? `load ${load1} / ${m.load_avg_5m??'—'} / ${m.load_avg_15m??'—'}`
    : '';
  const diskSub = m.disk_free_gb != null
    ? `${m.disk_free_gb} GB free of ${m.disk_total_gb} GB` : '';
  const ramSub  = m.ram_used_gb  != null
    ? `${m.ram_used_gb} / ${m.ram_total_gb} GB` : '';
  const cpuSub  = m.uptime_fmt   != null
    ? `uptime ${m.uptime_fmt}` : '';

  document.getElementById('metric-grid').innerHTML =
    metricCard('CPU', cpuPct, cpuWarn, cpuCrit, cpuSub) +
    metricCard('RAM', ramPct, ramWarn, ramCrit, ramSub) +
    metricCard('Disk', diskPct, diskWarn, diskCrit, diskSub) +
    (load1 != null
      ? `<div class="metric-item">
           <div class="metric-label"><span>Load avg</span><span class="metric-val">${load1}</span></div>
           <div class="gauge-bg"></div>
           <div class="metric-sub">${loadSub}</div>
         </div>`
      : '');

  // Active alerts
  const al = document.getElementById('alerts-list');
  if (m.alerts && m.alerts.length > 0) {
    const chips = m.alerts.map(a => `<span class="alert-chip chip-${sev}">${a}</span>`).join('');
    al.innerHTML = `<div style="margin-top:8px;font-size:11px;color:#6b7280;margin-bottom:4px;">Active alerts</div>${chips}`;
  } else {
    al.innerHTML = `<div style="margin-top:8px;"><span class="alert-chip chip-ok">All metrics within thresholds ✓</span></div>`;
  }
}

// ── Auto-refresh ───────────────────────────────────────────────────────
function toggleAutoRefresh(on) {
  _autoRefresh = on;
  if (on) {
    _autoRefreshTimer = setInterval(refreshMetrics, AUTO_REFRESH_MS);
  } else {
    clearInterval(_autoRefreshTimer);
  }
}

// ── Config ─────────────────────────────────────────────────────────────
let _cachedConfig = null;

async function loadConfig() {
  try {
    const cfg = await fetch('/alerts/config').then(r => r.json());
    _cachedConfig = cfg;
    const t = cfg.thresholds || {};
    document.getElementById('cpu-warn').value  = t.cpu_warn  ?? 75;
    document.getElementById('cpu-crit').value  = t.cpu_crit  ?? 90;
    document.getElementById('ram-warn').value  = t.ram_warn  ?? 80;
    document.getElementById('ram-crit').value  = t.ram_crit  ?? 92;
    document.getElementById('disk-warn').value = t.disk_warn ?? 80;
    document.getElementById('disk-crit').value = t.disk_crit ?? 90;
    document.getElementById('poll-interval').value  = cfg.poll_interval_seconds ?? 60;
    document.getElementById('cooldown').value        = cfg.cooldown_seconds      ?? 900;
  } catch(e) { console.error('config error', e); }
}

async function saveSettings() {
  const btn = document.getElementById('save-btn');
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await fetch('/alerts/thresholds', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        cpu_warn:  +document.getElementById('cpu-warn').value,
        cpu_crit:  +document.getElementById('cpu-crit').value,
        ram_warn:  +document.getElementById('ram-warn').value,
        ram_crit:  +document.getElementById('ram-crit').value,
        disk_warn: +document.getElementById('disk-warn').value,
        disk_crit: +document.getElementById('disk-crit').value,
      }),
    });
    await fetch('/alerts/poll', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        poll_interval_seconds: +document.getElementById('poll-interval').value,
        cooldown_seconds:       +document.getElementById('cooldown').value,
      }),
    });
    await loadConfig();
    const ok = document.getElementById('save-ok');
    ok.style.display = 'inline';
    setTimeout(() => ok.style.display = 'none', 2000);
  } catch(e) { console.error('save error', e); }
  btn.disabled = false; btn.textContent = 'Save settings';
}

// ── Chat ───────────────────────────────────────────────────────────────
async function ask(question) {
  const input  = document.getElementById('chat-input');
  const result = document.getElementById('chat-result');
  const btn    = document.getElementById('chat-send');
  const q = question || input.value.trim();
  if (!q) return;
  input.value = q;
  btn.disabled = true; btn.textContent = 'Thinking…';
  result.className = 'chat-result visible';
  result.textContent = 'Asking the agent…';
  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    result.textContent = data.answer || data.error || '(no response)';
  } catch(e) {
    result.textContent = 'Error: ' + e.message;
  }
  btn.disabled = false; btn.textContent = 'Ask';
}

// ── Alert log ──────────────────────────────────────────────────────────
async function loadAlertLog() {
  try {
    const entries = await fetch('/alerts/log').then(r => r.json());
    renderAlertLog(entries);
  } catch(e) { console.error('alert log error', e); }
}

function fmtTime(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function renderAlertLog(entries) {
  const body = document.getElementById('alert-log-body');
  if (!entries || entries.length === 0) {
    body.innerHTML = '<div class="empty-log">No alerts yet — monitor is running in background.</div>';
    return;
  }
  body.innerHTML = entries.map((e, i) => {
    const sevCls = 'sev-' + (e.severity || 'ok');
    const chips  = (e.alerts || []).map(a => `<span class="alert-chip chip-${e.severity||'ok'}">${a}</span>`).join('');
    const mets   = e.metrics || {};
    const metStr = [
      mets.cpu_pct  != null ? `CPU ${mets.cpu_pct}%`  : null,
      mets.ram_pct  != null ? `RAM ${mets.ram_pct}%`  : null,
      mets.disk_pct != null ? `Disk ${mets.disk_pct}%` : null,
    ].filter(Boolean).join('  ·  ');
    return `<div class="alert-entry">
      <div class="alert-entry-header" onclick="toggleEntry('ae-${i}')">
        <span class="alert-sev ${sevCls}">${e.severity || '?'}</span>
        <span class="alert-time">${fmtTime(e.timestamp)}</span>
        <span class="alert-metrics-mini">${metStr}</span>
        ${chips ? `<span class="alert-chips-row">${chips}</span>` : ''}
        <span class="alert-expand" id="ae-icon-${i}">▸</span>
      </div>
      <div class="alert-body" id="ae-${i}">${escHtml(e.diagnosis || '')}</div>
    </div>`;
  }).join('');
}

function toggleEntry(id) {
  const body = document.getElementById(id);
  const i    = id.replace('ae-', '');
  const icon = document.getElementById('ae-icon-' + i);
  if (body.classList.contains('open')) {
    body.classList.remove('open'); icon.textContent = '▸';
  } else {
    body.classList.add('open'); icon.textContent = '▾';
  }
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function triggerNow() {
  const btn = document.getElementById('trigger-btn');
  btn.disabled = true; btn.textContent = '⏳ Checking…';
  try {
    await fetch('/alerts/trigger', { method: 'POST' });
    await loadAlertLog();
  } catch(e) { console.error(e); }
  btn.disabled = false; btn.textContent = '▶ Check now';
}

// ── Init ───────────────────────────────────────────────────────────────
async function init() {
  await loadConfig();
  await refreshMetrics();
  await loadAlertLog();
  _autoRefreshTimer = setInterval(refreshMetrics, AUTO_REFRESH_MS);
  setInterval(loadAlertLog, 30000);
}

init();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Server Monitor — web UI")
    parser.add_argument("--host",     default="127.0.0.1")
    parser.add_argument("--port",     type=int, default=28767)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Server Monitor  →  http://{args.host}:{args.port}\n")
    _web(args.port)
