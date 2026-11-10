"""stdio filter in front of the official GitHub MCP server: drop null tool arguments.

CUGA (0.4.5) fills every optional parameter it did not set with null, e.g.
``{"owner": "o", "repo": "r", "sort": null, "head": null, "fields": null}``. The GitHub MCP server
(Go) validates arguments strictly against its JSON schema and refuses null where it wants a string
or an array: ``validating /properties/sort: has type "null", want "string"``. So every call that
leaves an optional parameter unset fails, and the agent retries until it gives up.

An unset optional argument and an absent one mean the same thing, so this filter removes the nulls
from ``tools/call`` requests and passes everything else through unchanged. The server's output is
not touched (it goes straight to our stdout). Remove this once CUGA stops sending nulls.

    python strip_nulls.py <server binary> [args...]
"""
from __future__ import annotations

import json
import subprocess
import sys


def strip(msg: dict) -> dict:
    """The message with null tool arguments removed (only for tools/call; anything else unchanged)."""
    if msg.get("method") == "tools/call":
        params = msg.get("params") or {}
        args = params.get("arguments")
        if isinstance(args, dict):
            params["arguments"] = {k: v for k, v in args.items() if v is not None}
    return msg


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: strip_nulls.py <server binary> [args...]", file=sys.stderr)
        return 2
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=None, stderr=None, text=True, bufsize=1)
    try:
        for line in sys.stdin:
            out = line
            try:
                msg = json.loads(line)
                if isinstance(msg, dict):
                    out = json.dumps(strip(msg)) + "\n"
            except ValueError:
                pass  # not JSON: pass it through as is
            child.stdin.write(out)
            child.stdin.flush()
    except BrokenPipeError:
        pass
    finally:
        try:
            child.stdin.close()
        except Exception:  # noqa: BLE001
            pass
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
