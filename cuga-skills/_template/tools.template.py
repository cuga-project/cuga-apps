"""Tools and helpers for the TODO_skill_name skill.

Dual-host: works as both an importable Python module AND a standalone CLI.

Native host (cuga-skills-ui)
    `from tools import TOOLS` — TOOLS is a list of LangChain `@tool`
    functions the host passes to `CugaAgent(tools=...)`. Requires
    `langchain_core` (soft dep — TOOLS is `[]` if missing).

Sandbox host (cuga start demo_skills + OpenSandbox)
    `python tools.py <command> <args...>` — stdlib-only CLI. The agent runs
    this via `run_command` and parses JSON from stdout. No langchain dep.

Both paths call the same underlying private `_<name>` pure helpers.

DELETE THIS FILE if the skill is pure (no live data, no I/O).
"""
from __future__ import annotations

import json
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Pure helpers — stdlib-only (or document any extra dep in SKILL.md
# frontmatter as `requirements:`). Used by both invocation paths.
# ---------------------------------------------------------------------------

def _tool_a(arg: str) -> dict:
    """TODO implement. Return JSON-serializable dict."""
    raise NotImplementedError


def _tool_b(arg1: str, arg2: int = 10) -> list[dict]:
    """TODO implement. Return JSON-serializable list."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Native-host path: LangChain @tool wrappers (soft dep on langchain_core).
# Each docstring is the API contract the model sees — be precise about
# units, defaults, return shape, edge cases.
# ---------------------------------------------------------------------------

try:
    from langchain_core.tools import tool

    @tool
    def tool_a(arg: str) -> dict:
        """TODO one-line trigger phrase the model uses to decide to call this.

        Args:
            arg: TODO what this is, units if numeric.

        Returns:
            TODO shape: {"key": str, ...} or {"error": str} on miss.
        """
        return _tool_a(arg)

    @tool
    def tool_b(arg1: str, arg2: int = 10) -> list[dict]:
        """TODO one-line trigger phrase.

        Args:
            arg1: TODO.
            arg2: TODO. Default 10.

        Returns:
            TODO shape and ordering. e.g.
            "Up to N records sorted by foo then bar, each: {name, ...}".
        """
        return _tool_b(arg1, arg2)

    TOOLS = [tool_a, tool_b]
except ImportError:
    TOOLS = []


# ---------------------------------------------------------------------------
# Sandbox-host path: CLI that emits JSON on stdout. Stdlib only.
# Usage:
#   python tools.py tool_a "value"
#   python tools.py tool_b "value1" 25
# ---------------------------------------------------------------------------

_USAGE = """\
usage:
  python tools.py tool_a <arg>
  python tools.py tool_b <arg1> [arg2=10]
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd = argv[1]
    try:
        if cmd == "tool_a":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            result: object = _tool_a(argv[2])
        elif cmd == "tool_b":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            arg2 = int(argv[3]) if len(argv) > 3 else 10
            result = _tool_b(argv[2], arg2)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr)
            return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
