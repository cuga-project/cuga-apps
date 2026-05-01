"""mcp-local — host-machine primitives.

Tools:
  - get_system_metrics()
  - list_top_processes(by, n)
  - check_disk_usage(path)
  - find_large_files(path, min_mb, max_results)
  - get_service_status(name)     systemctl (Linux only)

All tools read from the host the server runs on — so in Docker they see the
container's view, not the host's. Install with care: this grants read access
to process list + filesystem to anything that can reach the MCP endpoint.

transcribe_audio (faster-whisper) intentionally omitted in stage 1; will be
added alongside the voice_journal port in stage 2.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_LOCAL_PORT  # noqa: E402

mcp = make_server("mcp-local")


def _raw_metrics() -> dict:
    import psutil
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        load = os.getloadavg()
    except (AttributeError, OSError):
        load = (0.0, 0.0, 0.0)
    return {
        "cpu_percent":     psutil.cpu_percent(interval=0.5),
        "cpu_count":       psutil.cpu_count(),
        "memory_total_gb": round(vm.total / 1e9, 2),
        "memory_used_gb":  round(vm.used / 1e9, 2),
        "memory_percent":  vm.percent,
        "disk_total_gb":   round(disk.total / 1e9, 2),
        "disk_used_gb":    round(disk.used / 1e9, 2),
        "disk_percent":    disk.percent,
        "load_avg_1_5_15": load,
    }


@mcp.tool()
def get_system_metrics() -> str:
    """Return CPU / memory / disk / load snapshot of the host the MCP server runs on.

    Single point-in-time read — call repeatedly to observe change.
    """
    try:
        return tool_result(_raw_metrics())
    except ImportError:
        return tool_error("psutil not installed on the MCP server.", code="missing_dep")


@mcp.tool()
def get_system_metrics_with_alerts(thresholds: dict | None = None) -> str:
    """Return system metrics PLUS severity classification and an alerts list.

    Like get_system_metrics, but also classifies cpu/memory/disk against the
    given (or default) warning + critical thresholds and returns a derived
    `severity` ("ok" | "warning" | "critical") and a list of active `alerts`.
    Use this when the caller wants a single round-trip to know whether to page.

    Args:
        thresholds: Optional dict — any subset of:
            cpu_warn (default 75) · cpu_crit (90)
            ram_warn (80) · ram_crit (92)
            disk_warn (80) · disk_crit (90)

    Returns:
        Same fields as get_system_metrics plus:
            cpu_severity / ram_severity / disk_severity ∈ {"ok","warning","critical"}
            severity (worst of the three)
            alerts: list[str]  (e.g. ["CPU CRITICAL: 94%", "DISK WARNING: 85%"])
    """
    try:
        m = _raw_metrics()
    except ImportError:
        return tool_error("psutil not installed on the MCP server.", code="missing_dep")

    t = {
        "cpu_warn":  75, "cpu_crit":  90,
        "ram_warn":  80, "ram_crit":  92,
        "disk_warn": 80, "disk_crit": 90,
        **(thresholds or {}),
    }

    def _classify(value: float, warn: float, crit: float) -> str:
        if value >= crit: return "critical"
        if value >= warn: return "warning"
        return "ok"

    cpu_sev  = _classify(m["cpu_percent"],     t["cpu_warn"],  t["cpu_crit"])
    ram_sev  = _classify(m["memory_percent"],  t["ram_warn"],  t["ram_crit"])
    disk_sev = _classify(m["disk_percent"],    t["disk_warn"], t["disk_crit"])

    rank = {"ok": 0, "warning": 1, "critical": 2}
    overall = max([cpu_sev, ram_sev, disk_sev], key=lambda s: rank[s])

    alerts: list[str] = []
    if cpu_sev != "ok":
        alerts.append(f"CPU {cpu_sev.upper()}: {m['cpu_percent']:.0f}%")
    if ram_sev != "ok":
        alerts.append(f"RAM {ram_sev.upper()}: {m['memory_percent']:.0f}%")
    if disk_sev != "ok":
        alerts.append(f"DISK {disk_sev.upper()}: {m['disk_percent']:.0f}%")

    return tool_result({
        **m,
        "cpu_severity":  cpu_sev,
        "ram_severity":  ram_sev,
        "disk_severity": disk_sev,
        "severity":      overall,
        "alerts":        alerts,
        "thresholds":    t,
    })


@mcp.tool()
def list_top_processes(by: str = "cpu", n: int = 10) -> str:
    """List the top N processes sorted by CPU or memory usage.

    Args:
        by: "cpu" or "memory" (default "cpu").
        n: Number of processes to return (default 10, max 50).
    """
    try:
        import psutil
    except ImportError:
        return tool_error("psutil not installed on the MCP server.", code="missing_dep")
    key = by.lower()
    if key not in ("cpu", "memory"):
        return tool_error("by must be 'cpu' or 'memory'", code="bad_input")
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except psutil.Error:
            continue
    sort_key = "cpu_percent" if key == "cpu" else "memory_percent"
    procs.sort(key=lambda d: d.get(sort_key) or 0, reverse=True)
    return tool_result({"sort_by": key, "processes": procs[:min(n, 50)]})


@mcp.tool()
def check_disk_usage(path: str = "/") -> str:
    """Report disk usage (total/used/free GB, percent) at a filesystem path.

    Args:
        path: Filesystem path to check (default "/").
    """
    try:
        usage = shutil.disk_usage(path)
    except Exception as exc:
        return tool_error(f"disk_usage failed: {exc}", code="io")
    return tool_result({
        "path":     path,
        "total_gb": round(usage.total / 1e9, 2),
        "used_gb":  round(usage.used / 1e9, 2),
        "free_gb":  round(usage.free / 1e9, 2),
        "percent":  round(usage.used / usage.total * 100, 1),
    })


@mcp.tool()
def find_large_files(path: str, min_mb: int = 100, max_results: int = 20) -> str:
    """Walk a directory and list files larger than min_mb.

    Returns up to max_results, sorted largest-first.

    Args:
        path: Directory to walk.
        min_mb: Minimum size threshold in MB (default 100).
        max_results: Cap on results returned (default 20, max 200).
    """
    if not Path(path).exists():
        return tool_error(f"Path not found: {path}", code="not_found")
    min_bytes = int(min_mb) * 1024 * 1024
    results: list[dict] = []
    for root, _dirs, files in os.walk(path, followlinks=False):
        for name in files:
            fp = Path(root) / name
            try:
                size = fp.stat().st_size
                if size >= min_bytes:
                    results.append({"path": str(fp), "size_mb": round(size / 1024 / 1024, 1)})
            except OSError:
                continue
    results.sort(key=lambda d: d["size_mb"], reverse=True)
    return tool_result({"root": path, "matches": results[:min(max_results, 200)]})


@mcp.tool()
def get_service_status(name: str) -> str:
    """Check a systemd unit's status via `systemctl is-active` (Linux hosts only).

    Returns active / inactive / failed / unknown. Requires systemctl on PATH
    and sufficient permissions.

    Args:
        name: systemd unit name (e.g. "nginx", "sshd.service").
    """
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5,
        )
        state = proc.stdout.strip() or "unknown"
        return tool_result({"service": name, "state": state, "exit_code": proc.returncode})
    except FileNotFoundError:
        return tool_error("systemctl not available on this host.", code="unsupported")
    except Exception as exc:
        return tool_error(f"systemctl failed: {exc}", code="io")


@mcp.tool()
def transcribe_audio(file_path: str, language: str = "") -> str:
    """Transcribe an audio file to text via faster-whisper (runs locally on CPU).

    The file must be readable at `file_path` from inside the MCP server's
    container/host (bind-mount if needed). Supports wav, mp3, m4a, flac,
    ogg, and the common video containers ffmpeg can demux (mp4, mov, etc.).

    Args:
        file_path: Absolute path to the audio file.
        language: Optional 2-letter ISO code (e.g. "en", "es"). Auto-detect if empty.

    Env:
        WHISPER_MODEL — tiny | base | small | medium | large (default "base").
    """
    if not Path(file_path).exists():
        return tool_error(f"File not found: {file_path}", code="not_found")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return tool_error(
            "faster-whisper not installed on mcp-local. Rebuild the mcp image.",
            code="missing_dep",
        )
    model_size = os.getenv("WHISPER_MODEL", "base")
    try:
        model = WhisperModel(model_size, compute_type="int8")
        segments, info = model.transcribe(
            file_path,
            language=language or None,
            beam_size=5,
            vad_filter=True,
        )
        segs = [
            {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments
        ]
        full_text = " ".join(s["text"] for s in segs).strip()
        return tool_result({
            "language":         info.language,
            "language_prob":    round(info.language_probability, 3),
            "duration_seconds": round(info.duration, 2),
            "segments":         segs,
            "text":             full_text,
            "model":            model_size,
        })
    except Exception as exc:
        return tool_error(f"Transcription failed: {exc}", code="io")


if __name__ == "__main__":
    run(mcp, MCP_LOCAL_PORT)
