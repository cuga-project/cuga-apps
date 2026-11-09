"""mcp-repo-pulse — a GitHub repo's recent activity, with every number computed in code.

Tools:
  - daily_activity(repo, hours)   stars, merged PRs + reviewers, opened PRs/issues, closed issues,
                                  newcomers, top reviewers, releases, PRs waiting for review
  - activity(repo, minutes)       PRs opened/merged and issues opened/closed in the window, plus one
                                  moving number (activity_cursor) for a POLL's change gate
  - stars(repo)                   the star total, for a POLL on stars

Read-only. Built for scheduled reports: the agent calls this ONCE and writes text from the JSON,
instead of making 15-30 GitHub calls and counting by itself. Token: GITHUB_TOKEN from the file
$MCP_SECRETS_DIR/GITHUB_TOKEN (preferred) or the env.

Run:  python -m mcp_servers.repo_pulse.server            (streamable HTTP, MCP_REPO_PULSE_PORT)
      python -m mcp_servers.repo_pulse.server --stdio    (as a CUGA stdio subprocess)
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result
from mcp_servers._core.serve import make_server, run
from mcp_servers.repo_pulse import service
from apps._ports import MCP_REPO_PULSE_PORT  # noqa: E402

mcp = make_server("mcp-repo-pulse")


@mcp.tool()
def daily_activity(repo: str = "cuga-project/cuga-agent", hours: int = 24) -> str:
    """Everything that happened in a GitHub repo in the last `hours`, with all numbers computed.

    Returns stars (total, new, who), merged PRs (with reviewers), opened PRs and issues, closed
    issue count, newcomers (first PR or first issue), top reviewers, releases, and open PRs that
    have had no review for more than 5 days. Use the numbers exactly as returned; do not recount.

    Args:
        repo: owner/name, e.g. "cuga-project/cuga-agent".
        hours: Size of the window, ending now (default 24, max 744).
    """
    try:
        return tool_result(service.daily_activity(service.GitHub(), repo, hours))
    except ValueError as e:
        return tool_error(str(e), code="bad_input")
    except LookupError as e:
        return tool_error(str(e), code="not_found")
    except Exception as e:  # noqa: BLE001
        return tool_error(f"GitHub request failed: {e}", code="upstream")


@mcp.tool()
def activity(repo: str, minutes: int = 35) -> str:
    """What happened in a GitHub repo in the last `minutes`: PRs opened, PRs merged, issues opened,
    issues closed. Each list has count, items (at most 5: number, title, author, url, first_time)
    and more (how many were left out). nothing_new is true when all four are empty.
    activity_cursor is one number (the newest event time) that moves exactly when one of these
    events happens.

    Args:
        repo: owner/name, e.g. "cuga-project/cuga-agent".
        minutes: Size of the window, ending now (default 35, max 1440).
    """
    return _run(lambda: service.activity(service.GitHub(), repo, minutes))


@mcp.tool()
def stars(repo: str) -> str:
    """The current star total of a GitHub repo.

    Args:
        repo: owner/name, e.g. "cuga-project/cuga-agent".
    """
    return _run(lambda: service.stars(service.GitHub(), repo))


def _run(fn) -> str:
    try:
        return tool_result(fn())
    except ValueError as e:
        return tool_error(str(e), code="bad_input")
    except LookupError as e:
        return tool_error(str(e), code="not_found")
    except Exception as e:  # noqa: BLE001
        return tool_error(f"GitHub request failed: {e}", code="upstream")


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        run(mcp, MCP_REPO_PULSE_PORT)
