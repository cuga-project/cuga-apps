"""TODO_skill_name CLI helpers — stdlib only.

Rename this file to something descriptive (drop the .template suffix). The
agent runs it as a subprocess and parses JSON from stdout:

    python scripts/<filename>.py <command> <args...>

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.

If the skill needs pip deps beyond stdlib, declare them in SKILL.md
frontmatter as `requirements: [...]` so the host installs them before the
script runs.
"""
from __future__ import annotations

import json
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Pure helpers — public so the script's commands AND any importing host
# (e.g. local unit tests) can call them directly.
# ---------------------------------------------------------------------------

def tool_a(arg: str) -> dict:
    """TODO implement. Return JSON-serializable dict."""
    raise NotImplementedError


def tool_b(arg1: str, arg2: int = 10) -> list[dict]:
    """TODO implement. Return JSON-serializable list."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# CLI dispatcher
# ---------------------------------------------------------------------------

_USAGE = """\
usage:
  python scripts/<filename>.py tool_a <arg>
  python scripts/<filename>.py tool_b <arg1> [arg2=10]
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
            result: object = tool_a(argv[2])
        elif cmd == "tool_b":
            if len(argv) < 3:
                print(_USAGE, file=sys.stderr); return 2
            arg2 = int(argv[3]) if len(argv) > 3 else 10
            result = tool_b(argv[2], arg2)
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
