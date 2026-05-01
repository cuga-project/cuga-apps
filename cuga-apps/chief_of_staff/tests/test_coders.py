"""Tests for the Coder abstraction (LLMCoder + ClaudeCoder)."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from toolsmith.coders.base import CodeGenSpec, ProbeFailure  # noqa: E402
from toolsmith.coders.llm_coder import LLMCoder, _extract_code  # noqa: E402


class _StubLLM:
    """Captures last call and returns a canned response."""
    def __init__(self, response: str):
        self._response = response
        self.last_messages = None

    async def ainvoke(self, messages):
        self.last_messages = messages
        class _R:
            content = self._response
        return _R()


@pytest.mark.asyncio
async def test_llm_coder_generate_strips_fences():
    response = "```python\nasync def hello():\n    return 'world'\n```"
    coder = LLMCoder(llm=_StubLLM(response))
    result = await coder.generate_tool(CodeGenSpec(
        name="hello", description="x", parameters_schema={}, sample_input={},
    ))
    assert "async def hello" in result.code
    assert "```" not in result.code


@pytest.mark.asyncio
async def test_llm_coder_generate_handles_no_fence():
    response = "async def foo():\n    return 1"
    coder = LLMCoder(llm=_StubLLM(response))
    result = await coder.generate_tool(CodeGenSpec(
        name="foo", description="x", parameters_schema={}, sample_input={},
    ))
    assert "def foo" in result.code


@pytest.mark.asyncio
async def test_llm_coder_revise_includes_failure_context():
    coder = LLMCoder(llm=_StubLLM("async def fixed(): return 'ok'"))
    feedback = ProbeFailure(reason="http 404", status_code=404, response_excerpt="Not Found")
    from toolsmith.coders.base import CodeGenResult
    prior = CodeGenResult(code="async def broken(): pass", notes="")
    await coder.revise_tool(prior, feedback)

    text = " ".join(getattr(m, "content", str(m)) if not isinstance(m, dict) else m.get("content", "")
                    for m in coder._llm.last_messages)
    assert "404" in text
    assert "broken" in text


def test_extract_code_handles_python_tag():
    assert _extract_code("```python\nfoo\n```") == "foo"


def test_extract_code_handles_no_fence():
    assert _extract_code("just raw code\nhere") == "just raw code\nhere"


def test_extract_code_handles_py_alias():
    assert _extract_code("```py\nbar\n```") == "bar"


def test_coder_from_env_default():
    """Default selection should be gpt_oss (LLMCoder)."""
    import os
    from toolsmith.coders.base import coder_from_env
    os.environ.pop("TOOLSMITH_CODER", None)
    coder = coder_from_env()
    assert coder.name == "gpt_oss"


def test_coder_from_env_claude(monkeypatch):
    monkeypatch.setenv("TOOLSMITH_CODER", "claude")
    from toolsmith.coders.base import coder_from_env
    coder = coder_from_env()
    assert coder.name == "claude"


def test_coder_from_env_unknown_raises(monkeypatch):
    monkeypatch.setenv("TOOLSMITH_CODER", "doesnotexist")
    from toolsmith.coders.base import coder_from_env
    with pytest.raises(ValueError):
        coder_from_env()
