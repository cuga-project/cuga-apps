"""strip_nulls: CUGA sends null for unset optional args; the GitHub MCP server refuses them."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mcp_servers.github_official.strip_nulls import strip  # noqa: E402


def test_null_arguments_are_dropped_from_tool_calls():
    msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_pull_requests",
           "arguments": {"owner": "o", "repo": "r", "sort": None, "fields": None, "page": 1, "draft": False}}}
    assert strip(msg)["params"]["arguments"] == {"owner": "o", "repo": "r", "page": 1, "draft": False}


def test_other_messages_pass_through_unchanged():
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"x": None}}
    assert strip(dict(init)) == init
    assert strip({"jsonrpc": "2.0", "id": 3, "result": {"a": None}}) == {"jsonrpc": "2.0", "id": 3, "result": {"a": None}}
