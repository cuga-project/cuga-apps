"""
System metrics collection for the server health monitor.

Uses psutil (cross-platform) with stdlib fallbacks.
All functions return plain dicts — no agent framework dependency.

Install:
    pip install psutil
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Threshold defaults (override via env vars)
# ---------------------------------------------------------------------------

DISK_WARN_PCT  = float(os.getenv("DISK_THRESHOLD",  "80"))   # % used
DISK_CRIT_PCT  = float(os.getenv("DISK_CRITICAL",   "90"))
CPU_WARN_PCT   = float(os.getenv("CPU_THRESHOLD",   "75"))
CPU_CRIT_PCT   = float(os.getenv("CPU_CRITICAL",    "90"))
RAM_WARN_PCT   = float(os.getenv("RAM_THRESHOLD",   "80"))
RAM_CRIT_PCT   = float(os.getenv("RAM_CRITICAL",    "92"))
LOAD_WARN_MULT = float(os.getenv("LOAD_THRESHOLD",  "1.5"))   # × num_cpus


def _severity(value: float, warn: float, crit: float) -> str:
    if value >= crit:
        return "critical"
    if value >= warn:
        return "warning"
    return "ok"


# ---------------------------------------------------------------------------
# Core snapshot
# ---------------------------------------------------------------------------

def get_system_metrics() -> dict[str, Any]:
    """
    Return a health snapshot of the current machine.

    Always returns a dict; never raises (catches all errors gracefully).
    Keys: timestamp, hostname, cpu_pct, ram_pct, disk_pct,
          load_avg_1m, load_avg_5m, load_avg_15m, num_cpus,
          uptime_hours, swap_pct, severity, alerts
    """
    result: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "hostname":  platform.node(),
    }

    # -- CPU -----------------------------------------------------------------
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=1)
        load1, load5, load15 = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)
        num_cpus = psutil.cpu_count(logical=True) or 1
        result.update({
            "cpu_pct":       round(cpu_pct, 1),
            "load_avg_1m":   round(load1,   2),
            "load_avg_5m":   round(load5,   2),
            "load_avg_15m":  round(load15,  2),
            "num_cpus":      num_cpus,
        })
    except ImportError:
        # fallback: read /proc/loadavg on Linux
        try:
            la = Path("/proc/loadavg").read_text().split()[:3]
            result.update({
                "cpu_pct":      None,
                "load_avg_1m":  float(la[0]),
                "load_avg_5m":  float(la[1]),
                "load_avg_15m": float(la[2]),
                "num_cpus":     os.cpu_count() or 1,
            })
        except Exception:
            result.update({"cpu_pct": None, "load_avg_1m": None, "load_avg_5m": None,
                           "load_avg_15m": None, "num_cpus": os.cpu_count() or 1})

    # -- Memory --------------------------------------------------------------
    try:
        import psutil
        vm   = psutil.virtual_memory()
        swap = psutil.swap_memory()
        result.update({
            "ram_pct":        round(vm.percent,   1),
            "ram_used_gb":    round(vm.used  / 1e9, 2),
            "ram_total_gb":   round(vm.total / 1e9, 2),
            "swap_pct":       round(swap.percent, 1),
        })
    except ImportError:
        # fallback: /proc/meminfo on Linux
        try:
            lines = {k.strip(): v.strip()
                     for k, _, v in (l.partition(":") for l in Path("/proc/meminfo").read_text().splitlines() if l)}
            total = int(lines.get("MemTotal", "0 kB").split()[0]) * 1024
            avail = int(lines.get("MemAvailable", "0 kB").split()[0]) * 1024
            used  = total - avail
            result.update({
                "ram_pct":      round(used / total * 100, 1) if total else None,
                "ram_used_gb":  round(used  / 1e9, 2),
                "ram_total_gb": round(total / 1e9, 2),
                "swap_pct":     None,
            })
        except Exception:
            result.update({"ram_pct": None, "ram_used_gb": None, "ram_total_gb": None, "swap_pct": None})

    # -- Disk (root partition) -----------------------------------------------
    try:
        du = shutil.disk_usage("/")
        disk_pct = round(du.used / du.total * 100, 1) if du.total else 0
        result.update({
            "disk_pct":      disk_pct,
            "disk_used_gb":  round(du.used  / 1e9, 2),
            "disk_total_gb": round(du.total / 1e9, 2),
            "disk_free_gb":  round(du.free  / 1e9, 2),
        })
    except Exception:
        result.update({"disk_pct": None, "disk_used_gb": None, "disk_total_gb": None, "disk_free_gb": None})

    # -- Uptime --------------------------------------------------------------
    try:
        import psutil
        uptime_s = time.time() - psutil.boot_time()
        result["uptime_hours"] = round(uptime_s / 3600, 1)
        result["uptime_fmt"]   = str(timedelta(seconds=int(uptime_s)))
    except ImportError:
        try:
            uptime_s = float(Path("/proc/uptime").read_text().split()[0])
            result["uptime_hours"] = round(uptime_s / 3600, 1)
            result["uptime_fmt"]   = str(timedelta(seconds=int(uptime_s)))
        except Exception:
            result.update({"uptime_hours": None, "uptime_fmt": None})

    # -- Severity + Alerts ---------------------------------------------------
    alerts: list[str] = []

    cpu  = result.get("cpu_pct")
    ram  = result.get("ram_pct")
    disk = result.get("disk_pct")
    la1  = result.get("load_avg_1m")
    ncpu = result.get("num_cpus", 1) or 1

    if cpu  is not None and cpu  >= CPU_WARN_PCT:
        alerts.append(f"CPU {cpu}% (threshold {CPU_WARN_PCT}%)")
    if ram  is not None and ram  >= RAM_WARN_PCT:
        alerts.append(f"RAM {ram}% (threshold {RAM_WARN_PCT}%)")
    if disk is not None and disk >= DISK_WARN_PCT:
        alerts.append(f"Disk {disk}% (threshold {DISK_WARN_PCT}%)")
    if la1  is not None and la1  >= LOAD_WARN_MULT * ncpu:
        alerts.append(f"Load avg 1m={la1} > {LOAD_WARN_MULT}× {ncpu} CPUs")

    # Overall severity: worst of any individual metric
    severities = []
    if cpu  is not None: severities.append(_severity(cpu,  CPU_WARN_PCT,  CPU_CRIT_PCT))
    if ram  is not None: severities.append(_severity(ram,  RAM_WARN_PCT,  RAM_CRIT_PCT))
    if disk is not None: severities.append(_severity(disk, DISK_WARN_PCT, DISK_CRIT_PCT))

    sev_rank = {"ok": 0, "warning": 1, "critical": 2}
    overall = max(severities, key=lambda s: sev_rank.get(s, 0)) if severities else "ok"

    result["severity"] = overall
    result["alerts"]   = alerts

    return result


def has_alerts(metrics: dict) -> bool:
    """True when metrics contain at least one threshold breach."""
    return bool(metrics.get("alerts"))


# ---------------------------------------------------------------------------
# Process listing
# ---------------------------------------------------------------------------

def list_top_processes(by: str = "cpu", n: int = 10) -> list[dict[str, Any]]:
    """
    Return top-N processes sorted by CPU or memory usage.

    Args:
        by: "cpu" or "memory"
        n:  number of processes to return

    Returns:
        List of {pid, name, cpu_pct, ram_pct, ram_mb, status, cmdline}
    """
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "status", "cmdline",
                                       "cpu_percent", "memory_percent", "memory_info"]):
            try:
                info = p.info
                procs.append({
                    "pid":      info["pid"],
                    "name":     info["name"] or "",
                    "cpu_pct":  round(info.get("cpu_percent") or 0, 1),
                    "ram_pct":  round(info.get("memory_percent") or 0, 2),
                    "ram_mb":   round((info.get("memory_info") or type("o", (), {"rss": 0})()).rss / 1e6, 1),
                    "status":   info.get("status", ""),
                    "cmdline":  " ".join((info.get("cmdline") or [])[:6]),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        key = "cpu_pct" if by == "cpu" else "ram_mb"
        procs.sort(key=lambda p: p[key], reverse=True)
        return procs[:n]
    except ImportError:
        # Fallback: parse `ps aux` output
        try:
            out = subprocess.check_output(["ps", "aux"], text=True).splitlines()[1:]
            col = 2 if by == "cpu" else 3
            rows = sorted(out, key=lambda l: float(l.split()[col]), reverse=True)[:n]
            results = []
            for r in rows:
                p = r.split(None, 10)
                results.append({
                    "pid": p[1], "name": p[10][:40] if len(p) > 10 else "",
                    "cpu_pct": float(p[2]), "ram_pct": float(p[3]),
                    "ram_mb": None, "status": p[7], "cmdline": p[10] if len(p) > 10 else "",
                })
            return results
        except Exception as e:
            return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# Disk introspection
# ---------------------------------------------------------------------------

def check_disk_usage(path: str = "/", depth: int = 1) -> list[dict[str, Any]]:
    """
    Return disk usage of subdirectories under `path` up to `depth` levels.

    Uses du -sh for each direct child (safe, read-only).
    """
    try:
        target = Path(path).expanduser().resolve()
        if not target.is_dir():
            return [{"error": f"Not a directory: {path}"}]

        entries = []
        for child in sorted(target.iterdir()):
            try:
                if child.is_dir() and not child.is_symlink():
                    result = subprocess.run(
                        ["du", "-sh", str(child)],
                        capture_output=True, text=True, timeout=5,
                    )
                    size_str = result.stdout.split("\t")[0] if result.returncode == 0 else "?"
                    entries.append({"path": str(child), "size": size_str})
            except Exception:
                pass
        return entries
    except Exception as e:
        return [{"error": str(e)}]


def find_large_files(path: str = "/", min_mb: int = 100, top_n: int = 20) -> list[dict[str, Any]]:
    """
    Find the largest files under `path` that exceed `min_mb` MB.

    Uses `find` — read-only, safe on all POSIX systems.
    """
    try:
        min_kb = min_mb * 1024
        result = subprocess.run(
            ["find", str(Path(path).expanduser()), "-type", "f",
             "-size", f"+{min_kb}k", "-exec", "ls", "-lh", "{}", ";"],
            capture_output=True, text=True, timeout=30,
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        # Parse ls -lh output: permissions links owner group size date name
        files = []
        for line in lines:
            parts = line.split(None, 8)
            if len(parts) >= 9:
                files.append({"size": parts[4], "path": parts[8]})
        files.sort(key=lambda f: f["size"], reverse=True)
        return files[:top_n]
    except Exception as e:
        return [{"error": str(e)}]


# ---------------------------------------------------------------------------
# Service health
# ---------------------------------------------------------------------------

_ALLOWED_SERVICES = set(
    os.getenv("ALLOWED_SERVICES", "nginx,postgres,redis,docker,sshd,cron").split(",")
)


def get_service_status(service: str) -> dict[str, Any]:
    """
    Return status of a named system service (systemctl on Linux, launchctl on macOS).

    Only services in ALLOWED_SERVICES env var are checked (default: nginx, postgres, redis, docker, sshd, cron).
    """
    if service not in _ALLOWED_SERVICES:
        return {"error": f"Service '{service}' not in allowlist. Set ALLOWED_SERVICES to include it."}

    system = platform.system()
    try:
        if system == "Linux":
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True, text=True, timeout=5,
            )
            active = result.stdout.strip()
            result2 = subprocess.run(
                ["systemctl", "status", service, "--no-pager", "-n", "5"],
                capture_output=True, text=True, timeout=5,
            )
            return {"service": service, "active": active, "details": result2.stdout[-800:]}
        elif system == "Darwin":
            result = subprocess.run(
                ["launchctl", "list", service],
                capture_output=True, text=True, timeout=5,
            )
            return {
                "service": service,
                "active":  "running" if result.returncode == 0 else "stopped",
                "details": result.stdout[:800],
            }
        else:
            return {"service": service, "active": "unknown", "details": f"Unsupported OS: {system}"}
    except Exception as e:
        return {"service": service, "active": "error", "details": str(e)}
