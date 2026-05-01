#!/usr/bin/env python3
"""
launch.py — start / stop all cuga-apps processes in one shot.

In stage 1 this includes the 6 MCP servers + 4 reference apps. Other apps
from the old stack will come online as they're ported in stage 2; their
entries are commented out below.

Usage:
    python launch.py           # start everything (MCP servers + ready apps)
    python launch.py start
    python launch.py stop
    python launch.py status
    python launch.py logs
    python launch.py install

The port registry lives in _ports.py — do not hardcode ports here.
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from _ports import APP_PORTS, MCP_PORTS  # noqa: E402

PYTHON = sys.executable


def _app_cmd(script: str = "main.py") -> Callable[[int, dict], list]:
    def _cmd(port: int, env: dict) -> list:
        return [PYTHON, script, "--port", str(port)]
    return _cmd


def _port_env_cmd(script: str = "main.py") -> Callable[[int, dict], list]:
    def _cmd(port: int, env: dict) -> list:
        env["PORT"] = str(port)
        return [PYTHON, script]
    return _cmd


def _mcp_cmd(name: str) -> Callable[[int, dict], list]:
    def _cmd(_port: int, _env: dict) -> list:
        return [PYTHON, "-m", f"mcp_servers.{name}.server"]
    return _cmd


# ── Process registry ───────────────────────────────────────────────────────
# kind=mcp processes are launched from REPO_ROOT so the `mcp_servers.*` module
# path resolves. kind=app processes are launched from their own directory.

PROCS: list[dict] = [
    # MCP servers — stage 1 ships all six.
    dict(name="mcp-web",       kind="mcp", port=MCP_PORTS["web"],       cwd=REPO_ROOT,         cmd=_mcp_cmd("web")),
    dict(name="mcp-knowledge", kind="mcp", port=MCP_PORTS["knowledge"], cwd=REPO_ROOT,         cmd=_mcp_cmd("knowledge")),
    dict(name="mcp-geo",       kind="mcp", port=MCP_PORTS["geo"],       cwd=REPO_ROOT,         cmd=_mcp_cmd("geo")),
    dict(name="mcp-finance",   kind="mcp", port=MCP_PORTS["finance"],   cwd=REPO_ROOT,         cmd=_mcp_cmd("finance")),
    dict(name="mcp-code",      kind="mcp", port=MCP_PORTS["code"],      cwd=REPO_ROOT,         cmd=_mcp_cmd("code")),
    dict(name="mcp-local",     kind="mcp", port=MCP_PORTS["local"],     cwd=REPO_ROOT,         cmd=_mcp_cmd("local")),
    dict(name="mcp-text",      kind="mcp", port=MCP_PORTS["text"],      cwd=REPO_ROOT,         cmd=_mcp_cmd("text")),
    dict(name="mcp-invocable_apis", kind="mcp", port=MCP_PORTS["invocable_apis"], cwd=REPO_ROOT, cmd=_mcp_cmd("invocable_apis")),

    # Apps — all 23 are present after stage 2. Apps that delegate to MCP
    # servers share the mcp-* ports above; apps that kept inline tools are
    # genuinely self-contained (app-state or heavy/auth-specific).
    dict(name="web_researcher",     kind="app", port=APP_PORTS["web_researcher"],     cwd=HERE / "web_researcher",     cmd=_app_cmd()),
    dict(name="paper_scout",        kind="app", port=APP_PORTS["paper_scout"],        cwd=HERE / "paper_scout",        cmd=_app_cmd()),
    dict(name="travel_planner",     kind="app", port=APP_PORTS["travel_planner"],     cwd=HERE / "travel_planner",     cmd=_port_env_cmd()),
    dict(name="code_reviewer",      kind="app", port=APP_PORTS["code_reviewer"],      cwd=HERE / "code_reviewer",      cmd=_app_cmd()),
    dict(name="newsletter",         kind="app", port=APP_PORTS["newsletter"],         cwd=HERE / "newsletter",         cmd=_app_cmd()),
    dict(name="drop_summarizer",    kind="app", port=APP_PORTS["drop_summarizer"],    cwd=HERE / "drop_summarizer",    cmd=_app_cmd()),
    dict(name="voice_journal",      kind="app", port=APP_PORTS["voice_journal"],      cwd=HERE / "voice_journal",      cmd=_app_cmd()),
    dict(name="smart_todo",         kind="app", port=APP_PORTS["smart_todo"],         cwd=HERE / "smart_todo",         cmd=_app_cmd()),
    dict(name="server_monitor",     kind="app", port=APP_PORTS["server_monitor"],     cwd=HERE / "server_monitor",     cmd=_app_cmd()),
    dict(name="stock_alert",        kind="app", port=APP_PORTS["stock_alert"],        cwd=HERE / "stock_alert",        cmd=_app_cmd()),
    dict(name="video_qa",           kind="app", port=APP_PORTS["video_qa"],           cwd=HERE / "video_qa",           cmd=lambda p, e: [PYTHON, "run.py", "--web", "--port", str(p)]),
    dict(name="deck_forge",         kind="app", port=APP_PORTS["deck_forge"],         cwd=HERE / "deck_forge",         cmd=_app_cmd()),
    dict(name="youtube_research",   kind="app", port=APP_PORTS["youtube_research"],   cwd=HERE / "youtube_research",   cmd=_app_cmd()),
    dict(name="arch_diagram",       kind="app", port=APP_PORTS["arch_diagram"],       cwd=HERE / "arch_diagram",       cmd=_app_cmd()),
    dict(name="hiking_research",    kind="app", port=APP_PORTS["hiking_research"],    cwd=HERE / "hiking_research",    cmd=_app_cmd()),
    dict(name="movie_recommender",  kind="app", port=APP_PORTS["movie_recommender"],  cwd=HERE / "movie_recommender",  cmd=_app_cmd()),
    dict(name="webpage_summarizer", kind="app", port=APP_PORTS["webpage_summarizer"], cwd=HERE / "webpage_summarizer", cmd=_app_cmd()),
    dict(name="wiki_dive",          kind="app", port=APP_PORTS["wiki_dive"],          cwd=HERE / "wiki_dive",          cmd=_app_cmd()),
    dict(name="box_qa",             kind="app", port=APP_PORTS["box_qa"],             cwd=HERE / "box_qa",             cmd=_app_cmd()),
    dict(name="api_doc_gen",        kind="app", port=APP_PORTS["api_doc_gen"],        cwd=HERE / "api_doc_gen",        cmd=_app_cmd()),
    dict(name="ibm_cloud_advisor",  kind="app", port=APP_PORTS["ibm_cloud_advisor"],  cwd=HERE / "ibm_cloud_advisor",  cmd=_app_cmd()),
    dict(name="ibm_docs_qa",        kind="app", port=APP_PORTS["ibm_docs_qa"],        cwd=HERE / "ibm_docs_qa",        cmd=_app_cmd()),
    dict(name="ibm_whats_new",      kind="app", port=APP_PORTS["ibm_whats_new"],      cwd=HERE / "ibm_whats_new",      cmd=_app_cmd()),
    dict(name="bird_invocable_api_creator", kind="app", port=APP_PORTS["bird_invocable_api_creator"], cwd=HERE / "bird_invocable_api_creator", cmd=_app_cmd()),
    dict(name="brief_budget",       kind="app", port=APP_PORTS["brief_budget"],       cwd=HERE / "brief_budget",       cmd=_app_cmd()),
    dict(name="trip_designer",      kind="app", port=APP_PORTS["trip_designer"],      cwd=HERE / "trip_designer",      cmd=_app_cmd()),
    dict(name="code_engine_deployer", kind="app", port=APP_PORTS["code_engine_deployer"], cwd=HERE / "code_engine_deployer", cmd=_app_cmd()),
    dict(name="recipe_composer",    kind="app", port=APP_PORTS["recipe_composer"],    cwd=HERE / "recipe_composer",    cmd=_app_cmd()),
    dict(name="city_beat",          kind="app", port=APP_PORTS["city_beat"],          cwd=HERE / "city_beat",          cmd=_app_cmd()),
]

PID_FILE = HERE / ".launch_pids"


# ── .env loader ────────────────────────────────────────────────────────────

def _load_env(env_path: Path) -> dict:
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.split("#")[0].strip().strip("'\"")
    return env


# ── Port plumbing ──────────────────────────────────────────────────────────

def _pid_on_port(port: int) -> Optional[int]:
    try:
        r = subprocess.run(
            ["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True,
        )
        pids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None


def _claim_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            pass
    pid = _pid_on_port(port)
    if pid is None:
        return False
    print(f"  [EVICT] port {port} held by pid={pid} — SIGTERM")
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    for _ in range(15):
        time.sleep(0.2)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                continue
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    time.sleep(0.5)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


# ── PID file ───────────────────────────────────────────────────────────────

def _read_pids() -> list[tuple[str, int, int]]:
    if not PID_FILE.exists():
        return []
    out = []
    for line in PID_FILE.read_text().splitlines():
        parts = line.split()
        if len(parts) == 3:
            out.append((parts[0], int(parts[1]), int(parts[2])))
    return out


def _write_pids(records: list[tuple[str, int, int]]) -> None:
    PID_FILE.write_text("".join(f"{n} {p} {pid}\n" for n, p, pid in records))


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_start(filter_names: Optional[list[str]], env_file: Path) -> None:
    dotenv = _load_env(env_file)
    merged_env = {**os.environ, **dotenv}

    existing = {name: (port, pid) for name, port, pid in _read_pids() if _is_running(pid)}
    records = [r for r in _read_pids() if _is_running(r[2])]

    targets = [p for p in PROCS if (not filter_names or p["name"] in filter_names)]

    # MCP servers first — apps need them up to initialise.
    targets.sort(key=lambda p: (p["kind"] != "mcp", p["name"]))

    for proc in targets:
        name = proc["name"]
        port = proc["port"]
        if name in existing:
            print(f"  [SKIP]   {name:20s} already running on port={existing[name][0]}")
            continue
        if not _claim_port(port):
            print(f"  [ERROR]  {name:20s} could not free port {port}")
            continue
        command = proc["cmd"](port, merged_env)
        log_path = HERE / f".{name}.log"
        with open(log_path, "w") as log_fh:
            popen = subprocess.Popen(
                command,
                cwd=str(proc["cwd"]),
                env=merged_env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        records = [r for r in records if r[0] != name]
        records.append((name, port, popen.pid))
        print(f"  [START]  {name:20s} port={port} pid={popen.pid} log={log_path.name}")
        # Small pause between MCP starts so HTTP servers actually bind before
        # the next app tries to connect.
        if proc["kind"] == "mcp":
            time.sleep(0.3)

    _write_pids(records)


def cmd_stop(filter_names: Optional[list[str]]) -> None:
    remaining = []
    for name, port, pid in _read_pids():
        if filter_names and name not in filter_names:
            remaining.append((name, port, pid))
            continue
        if _is_running(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            print(f"  [STOP]   {name:20s} pid={pid}")
        else:
            print(f"  [GONE]   {name:20s} pid={pid} (already dead)")
    _write_pids(remaining)


def cmd_status() -> None:
    records = _read_pids()
    if not records:
        print("No processes tracked.")
        return
    print(f"  {'Process':<20}  {'Port':>6}  {'PID':>7}  Status")
    print(f"  {'-'*20}  {'-'*6}  {'-'*7}  ------")
    for name, port, pid in records:
        print(f"  {name:<20}  {port:>6}  {pid:>7}  {'running' if _is_running(pid) else 'stopped'}")


def cmd_logs(filter_names: Optional[list[str]], tail: int = 30) -> None:
    targets = [p["name"] for p in PROCS if (not filter_names or p["name"] in filter_names)]
    for name in targets:
        log_path = HERE / f".{name}.log"
        if not log_path.exists():
            print(f"=== {name} — no log ===\n")
            continue
        lines = log_path.read_text().splitlines()[-tail:]
        print(f"=== {name} (last {len(lines)}) ===")
        print("\n".join(lines))
        print()


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Start/stop cuga-apps MCP stack.")
    parser.add_argument("action", nargs="?", default="start",
                        choices=["start", "stop", "status", "logs"])
    parser.add_argument("names", nargs="*", help="Optional process-name filter")
    parser.add_argument("--env", type=Path, default=HERE / ".env")
    parser.add_argument("--tail", type=int, default=30)
    args = parser.parse_args()

    filter_names = args.names or None
    print(f"\n=== cuga-apps launcher — {args.action.upper()} ===\n")
    if args.action == "start":
        cmd_start(filter_names, args.env)
    elif args.action == "stop":
        cmd_stop(filter_names)
    elif args.action == "status":
        cmd_status()
    elif args.action == "logs":
        cmd_logs(filter_names, args.tail)


if __name__ == "__main__":
    main()
