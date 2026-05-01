"""Feed tools for Newsletter Intelligence — delegated to mcp-web."""
from __future__ import annotations


def make_feed_tools():
    from _mcp_bridge import load_tools
    return load_tools(["web"])
