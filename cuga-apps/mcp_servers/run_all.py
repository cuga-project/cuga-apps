"""Run all 8 MCP servers in one terminal — local-dev convenience launcher.

Usage (from cuga-apps/):
    pip install -r requirements.mcp.txt
    python -m mcp_servers.run_all

Each server is spawned as a subprocess; their stdout/stderr is multiplexed
into this process with a `[mcp-<name>]` prefix per line so you can tell who
said what. Ctrl-C cleanly terminates every child.

This is a dev convenience — production / shared envs should use docker-compose.
"""
from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps._ports import MCP_PORTS  # noqa: E402


def _stream(name: str, pipe) -> None:
    prefix = f"[mcp-{name:<14s}] "
    for raw in iter(pipe.readline, b""):
        sys.stdout.write(prefix + raw.decode(errors="replace"))
        sys.stdout.flush()


def main() -> int:
    procs: list[tuple[str, subprocess.Popen]] = []

    for name, port in MCP_PORTS.items():
        cmd = [sys.executable, "-m", f"mcp_servers.{name}.server"]
        p = subprocess.Popen(
            cmd,
            cwd=str(_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        procs.append((name, p))
        threading.Thread(target=_stream, args=(name, p.stdout), daemon=True).start()
        print(f"[run_all        ] launched mcp-{name} (pid={p.pid}) on :{port}")

    shutting_down = False

    def shutdown(*_):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print("\n[run_all        ] stopping all servers…")
        for _, p in procs:
            if p.poll() is None:
                p.terminate()
        deadline = time.time() + 5
        for _, p in procs:
            remaining = max(0.1, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Watch loop: if any child dies, tear the rest down so failures are loud.
    while True:
        for name, p in procs:
            if p.poll() is not None:
                print(
                    f"[run_all        ] mcp-{name} exited (code={p.returncode}); "
                    "shutting the rest down"
                )
                shutdown()
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main() or 0)
