"""
Unit tests for Wikipedia URL construction in mcp-knowledge. Article titles go
into the URL path, so characters like "?" and "%" must be percent-encoded:
unencoded, https://en.wikipedia.org/wiki/What?_(film) serves the "What"
article, not "What? (film)".
"""
from __future__ import annotations

import json

import pytest

from mcp_servers.knowledge import server as knowledge_server

pytestmark = pytest.mark.unit


def test_search_wikipedia_encodes_title_in_url(monkeypatch):
    monkeypatch.setattr(knowledge_server, "get_json", lambda url, params=None: {
        "query": {"search": [
            {"title": "What? (film)", "snippet": "a 1972 film"},
            {"title": "100% (song)", "snippet": "a song"},
        ]}
    })
    out = json.loads(knowledge_server.search_wikipedia("what film"))

    assert out["ok"] is True
    urls = [r["url"] for r in out["data"]["results"]]
    assert urls[0] == "https://en.wikipedia.org/wiki/What%3F_%28film%29"
    assert urls[1] == "https://en.wikipedia.org/wiki/100%25_%28song%29"


def test_wikipedia_article_fallback_url_is_encoded(monkeypatch):
    # No fullurl in the reply, so the URL is built from the requested title.
    monkeypatch.setattr(knowledge_server, "get_json", lambda url, params=None: {
        "query": {"pages": {"123": {
            "pageid": 123,
            "title": "What? (film)",
            "extract": "A 1972 comedy film.",
        }}}
    })
    out = json.loads(knowledge_server.get_wikipedia_article("What? (film)"))

    assert out["ok"] is True
    assert out["data"]["url"] == "https://en.wikipedia.org/wiki/What%3F_%28film%29"
    assert out["data"]["summary"] == "A 1972 comedy film."


def test_wikipedia_article_prefers_canonical_fullurl(monkeypatch):
    monkeypatch.setattr(knowledge_server, "get_json", lambda url, params=None: {
        "query": {"pages": {"123": {
            "pageid": 123,
            "title": "What? (film)",
            "fullurl": "https://en.wikipedia.org/wiki/What%3F_(film)",
            "extract": "A 1972 comedy film.",
        }}}
    })
    out = json.loads(knowledge_server.get_wikipedia_article("What? (film)"))

    assert out["ok"] is True
    assert out["data"]["url"] == "https://en.wikipedia.org/wiki/What%3F_(film)"
