"""
Opt-in: live LLM round-trips against each app's main inference endpoint.

These cost real tokens and take real time (often 10-60s per app). Run only
with `pytest -m llm` (or `make test-llm`). They check that the agent
plumbing — tool list, system prompt, MCP bridge — actually works
end-to-end with whatever LLM provider is configured in your .env.

If a tool list breaks (e.g. a renamed MCP tool the prompt still references),
this catches it. If the LLM provider is unreachable or the API key is
missing, the test skips with a clear message.
"""
from __future__ import annotations

import os

import httpx
import pytest

from .conftest import app_url


pytestmark = pytest.mark.llm


def _have_an_llm_key() -> bool:
    return any(os.getenv(k) for k in (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "RITS_API_KEY",
        "WATSONX_APIKEY", "LITELLM_API_KEY", "OLLAMA_BASE_URL",
    ))


# (app, endpoint, payload, response_field)
LLM_PROBES = [
    ("paper_scout",   "/ask",    {"question": "What is arXiv ID 1706.03762?"}, "answer"),
    ("code_reviewer", "/review", {"snippet": "def f(x): return x+1"},          "review"),
    ("wiki_dive",     "/ask",    {"question": "Tell me about Alan Turing."},   "answer"),
    ("web_researcher", "/ask",   {"question": "Latest AI safety research, 1-2 lines"}, "answer"),
]


@pytest.fixture(scope="module", autouse=True)
def _need_llm_key():
    if not _have_an_llm_key():
        pytest.skip(
            "no LLM provider key set — these tests need ANTHROPIC_API_KEY, "
            "OPENAI_API_KEY, RITS_API_KEY, WATSONX_APIKEY, LITELLM_API_KEY, "
            "or OLLAMA_BASE_URL"
        )


@pytest.mark.parametrize("app,endpoint,payload,field", LLM_PROBES, ids=[a for a, *_ in LLM_PROBES])
def test_llm_round_trip(app, endpoint, payload, field):
    url = app_url(app) + endpoint
    try:
        # LLMs are slow — give them three minutes max.
        r = httpx.post(url, json=payload, timeout=180.0)
    except httpx.HTTPError as exc:
        pytest.fail(f"{app} unreachable: {exc}")

    assert r.status_code in (200, 201), f"{app} returned {r.status_code}: {r.text[:300]}"

    body = r.json()
    if "error" in body:
        pytest.fail(f"{app} reported agent error: {body['error']}")
    assert field in body, f"{app} response missing '{field}' field: keys={list(body)}"
    answer = body[field]
    assert isinstance(answer, str)
    assert answer.strip(), f"{app} returned an empty {field}"


def test_drop_summarizer_pipeline_uses_mcp_text(http):
    """End-to-end test of the drop_summarizer file → mcp-text → LLM pipeline.

    Posts a small text file to drop_summarizer's upload endpoint, polls until
    a summary appears in /summaries, and confirms the file showed up. This
    exercises:
        drop_summarizer file watcher
        → _extract() (calls mcp-text via _mcp_bridge.call_tool)
        → CugaAgent invoke (LLM round-trip)
        → SQLite persistence
    """
    import time

    base = app_url("drop_summarizer")

    # 1. snapshot existing summary count
    before = len(http.get(base + "/summaries", timeout=15).json())

    # 2. upload a tiny text file (the watcher should pick it up)
    text = "Project Alpha is on track. Q3 milestones met. Risk: vendor delays."
    files = {"file": ("alpha-status.txt", text, "text/plain")}
    r = http.post(base + "/upload", files=files, timeout=30)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text[:200]}"

    # 3. poll for up to 3 minutes for a new summary to land.
    deadline = time.time() + 180
    new_count = before
    while time.time() < deadline:
        new_count = len(http.get(base + "/summaries", timeout=15).json())
        if new_count > before:
            break
        time.sleep(5)
    assert new_count > before, (
        f"no new summary appeared within 180s (before={before}, after={new_count})"
    )
