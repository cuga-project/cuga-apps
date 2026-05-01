"""Uniform tool-return envelope so every MCP tool speaks the same shape.

All tools return a JSON string. On success: {"ok": true, "data": …}
On failure: {"ok": false, "error": "...", "code": "..."}

Keeps LLMs from guessing at error shapes across servers.
"""
from __future__ import annotations

import json
from typing import Any


def tool_result(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, ensure_ascii=False)


def tool_error(message: str, code: str = "error") -> str:
    return json.dumps({"ok": False, "error": message, "code": code}, ensure_ascii=False)
