"""Tests for the [[TOOL_GAP]] marker parser in the cuga adapter."""

import sys
from pathlib import Path

# adapters/cuga/server.py expects to be importable as a package, but for unit
# tests we just sys.path it directly — tests don't need the cuga.sdk import
# path resolution to fire (we only test the pure parser).
_ADAPTER = Path(__file__).resolve().parent.parent / "adapters" / "cuga"
sys.path.insert(0, str(_ADAPTER))

# Stub the heavy imports the module pulls in at top-level so this test
# doesn't need cuga.sdk / langchain installed.
import types  # noqa: E402
for mod in ("_mcp_bridge", "_llm"):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

# Now import the function we actually want to test.
from server import _parse_gap  # noqa: E402


def test_no_marker_returns_unchanged():
    answer = "Here is the weather in Paris: 18C and sunny."
    cleaned, gap = _parse_gap(answer)
    assert cleaned == answer
    assert gap is None


def test_marker_with_valid_json_strips_and_parses():
    answer = (
        "I can't answer that without a weather tool.\n"
        '[[TOOL_GAP]]\n{"capability": "weather lookup", "inputs": ["city"], "expected_output": "current weather"}'
    )
    cleaned, gap = _parse_gap(answer)
    assert "TOOL_GAP" not in cleaned
    assert "weather tool" in cleaned
    assert gap == {
        "capability": "weather lookup",
        "inputs": ["city"],
        "expected_output": "current weather",
    }


def test_marker_with_invalid_json_keeps_answer_returns_no_gap():
    answer = "Sorry.\n[[TOOL_GAP]]\n{not valid json}"
    cleaned, gap = _parse_gap(answer)
    # Parser should fail-safe: keep the original answer and return no gap.
    assert gap is None
    assert "Sorry" in cleaned


def test_marker_inline_with_json_works():
    answer = '[[TOOL_GAP]] {"capability": "x"}'
    cleaned, gap = _parse_gap(answer)
    assert gap == {"capability": "x"}
    assert cleaned == ""
