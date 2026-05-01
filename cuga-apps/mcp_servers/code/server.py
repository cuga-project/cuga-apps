"""mcp-code — code-analysis primitives.

Tools:
  - check_python_syntax(code)   AST validation
  - extract_code_metrics(code)  LOC, branch complexity, top-level defs
  - detect_language(code)       heuristic language ID

stdlib-only — no external APIs.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_result
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_CODE_PORT  # noqa: E402

mcp = make_server("mcp-code")


@mcp.tool()
def check_python_syntax(code: str) -> str:
    """Check a Python code snippet for syntax errors using the AST parser.

    Returns {valid: bool, error: str|null, line: int|null, col: int|null}.
    Use this first whenever the code appears to be Python.

    Args:
        code: Python source code.
    """
    try:
        ast.parse(code)
        return tool_result({"valid": True, "error": None, "line": None, "col": None})
    except SyntaxError as e:
        return tool_result({
            "valid": False,
            "error": str(e),
            "line":  e.lineno,
            "col":   e.offset,
        })


@mcp.tool()
def extract_code_metrics(code: str) -> str:
    """Extract basic structural metrics from a code snippet.

    Returns line count, non-blank line count, estimated cyclomatic complexity
    (counted from branching keywords), and — for Python only — a list of
    top-level function/class definitions.

    Args:
        code: Source code in any language.
    """
    lines = code.splitlines()
    total = len(lines)
    non_blank = sum(1 for ln in lines if ln.strip())
    branch_kws = ("if ", "elif ", "else:", "for ", "while ", "except",
                  "case ", "&&", "||", "? ", "?? ")
    complexity = sum(1 for ln in lines for kw in branch_kws if kw in ln)

    top_level: list[str] = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_level.append(f"{type(node).__name__}:{node.name}")
    except Exception:
        pass

    return tool_result({
        "total_lines":     total,
        "non_blank_lines": non_blank,
        "branch_complexity_estimate": complexity,
        "top_level_definitions": top_level,
    })


@mcp.tool()
def detect_language(code: str) -> str:
    """Heuristically identify the programming language of a snippet.

    Scores the snippet against marker tokens for ~14 common languages.
    Returns {language, confidence} with confidence ∈ {high, medium, low}.

    Args:
        code: Source code snippet.
    """
    cl = code.lower()
    checks = {
        "python":     ["def ", "import ", "from ", "elif", "print(", "self.", "__init__", ":"],
        "javascript": ["const ", "let ", "var ", "function ", "=>", "console.log", "require(", "export "],
        "typescript": ["interface ", ": string", ": number", ": boolean", "type ", "<T>", "tsx"],
        "java":       ["public class", "private ", "static void", "system.out", "import java"],
        "go":         ["func ", "package ", ":=", "fmt.", "goroutine", "chan "],
        "rust":       ["fn ", "let mut", "impl ", "use std", "println!", "match "],
        "cpp":        ["#include", "std::", "cout <<", "int main", "nullptr", "->"],
        "c":          ["#include <stdio", "printf(", "int main", "malloc(", "->"],
        "ruby":       ["def ", "end\n", "puts ", "attr_", "do |", ".each"],
        "php":        ["<?php", "$_", "echo ", "function ", "->", "array("],
        "sql":        ["select ", "from ", "where ", "insert into", "create table", "join "],
        "html":       ["<!doctype", "<html", "<div", "<body", "</", "class="],
        "css":        ["{", "}", "color:", "margin:", "padding:", "display:"],
        "bash":       ["#!/bin/bash", "echo ", "fi\n", "done\n", "$1", "grep "],
    }
    scores = {lang: sum(1 for p in patterns if p in cl) for lang, patterns in checks.items()}
    if not any(scores.values()):
        return tool_result({"language": "unknown", "confidence": "low"})
    best = max(scores, key=lambda k: scores[k])
    score = scores[best]
    conf = "high" if score >= 3 else "medium" if score >= 1 else "low"
    return tool_result({"language": best, "confidence": conf})


if __name__ == "__main__":
    run(mcp, MCP_CODE_PORT)
