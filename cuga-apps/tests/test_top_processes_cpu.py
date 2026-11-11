"""
Unit tests for CPU sampling in mcp-local's list_top_processes.
psutil answers 0.0 the first time a Process's cpu_percent is read (the call
only establishes a measurement baseline), and the tool built fresh Process
handles on every invocation — so sorting by "cpu" ranked every process at
0.0% and returned them in process-table order instead of by actual usage.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

from mcp_servers.local import server as local_server

pytestmark = pytest.mark.unit


class _FakeError(Exception):
    pass


class _FakeProc:
    """First cpu_percent read returns 0.0, later reads the measured value."""

    def __init__(self, pid, name, cpu, mem, dies_after_prime=False):
        self._cpu = cpu
        self._primed = False
        self._dies = dies_after_prime
        self._attrs = {
            "pid": pid, "name": name, "username": "u",
            "cpu_percent": 0.0, "memory_percent": mem,
        }
        self.info = None

    def _iter_info(self, attrs):
        if "cpu_percent" in attrs:
            self._primed = True
        self.info = {a: self._attrs[a] for a in attrs}
        return self

    def cpu_percent(self, interval=None):
        if self._dies and self._primed:
            raise _FakeError("process gone")
        if not self._primed:
            self._primed = True
            return 0.0
        return self._cpu


def _install_fake_psutil(monkeypatch, procs):
    fake = types.ModuleType("psutil")
    fake.Error = _FakeError
    fake.process_iter = lambda attrs=None: iter(p._iter_info(attrs or []) for p in procs)
    monkeypatch.setitem(sys.modules, "psutil", fake)
    monkeypatch.setattr("time.sleep", lambda s: None)


def test_cpu_sort_ranks_by_measured_usage(monkeypatch):
    # process-table order is the reverse of real CPU usage
    procs = [
        _FakeProc(1, "idle_daemon", cpu=0.5, mem=1.0),
        _FakeProc(2, "busy_worker", cpu=92.0, mem=2.0),
        _FakeProc(3, "medium_job", cpu=40.0, mem=3.0),
    ]
    _install_fake_psutil(monkeypatch, procs)

    out = json.loads(local_server.list_top_processes("cpu", 10))

    names = [p["name"] for p in out["data"]["processes"]]
    assert names == ["busy_worker", "medium_job", "idle_daemon"]


def test_cpu_values_are_the_measured_ones(monkeypatch):
    procs = [_FakeProc(1, "busy_worker", cpu=92.0, mem=2.0)]
    _install_fake_psutil(monkeypatch, procs)

    out = json.loads(local_server.list_top_processes("cpu", 10))

    assert out["data"]["processes"][0]["cpu_percent"] == 92.0


def test_process_gone_between_reads_is_skipped(monkeypatch):
    procs = [
        _FakeProc(1, "survivor", cpu=10.0, mem=1.0),
        _FakeProc(2, "short_lived", cpu=50.0, mem=2.0, dies_after_prime=True),
    ]
    _install_fake_psutil(monkeypatch, procs)

    out = json.loads(local_server.list_top_processes("cpu", 10))

    names = [p["name"] for p in out["data"]["processes"]]
    assert names == ["survivor"]


def test_memory_sort_still_works(monkeypatch):
    procs = [
        _FakeProc(1, "small", cpu=5.0, mem=1.0),
        _FakeProc(2, "large", cpu=1.0, mem=9.0),
    ]
    _install_fake_psutil(monkeypatch, procs)

    out = json.loads(local_server.list_top_processes("memory", 10))

    names = [p["name"] for p in out["data"]["processes"]]
    assert names == ["large", "small"]
