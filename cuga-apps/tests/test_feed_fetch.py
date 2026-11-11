"""
Unit tests for feed fetching in mcp-web: fetch_feed and search_feeds must go
through the shared HTTP layer instead of letting feedparser fetch the URL
itself (feedparser's own fetching has no timeout, UA, or retry).

These run in-process — the only socket used is a local stalled server that
proves the timeout path.
"""
from __future__ import annotations

import json
import socket
import threading
import time

import pytest

from mcp_servers._core import http as core_http
from mcp_servers.web import server as web_server

pytestmark = pytest.mark.unit

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Example Feed</title>
<item><title>Agents in production</title><link>http://x/1</link>
<description>Deploying LLM agents safely.</description></item>
<item><title>Weekly notes</title><link>http://x/2</link>
<description>Nothing relevant here.</description></item>
</channel></rss>"""


def test_fetch_feed_fetches_via_shared_http_layer(monkeypatch):
    fetched = []

    def fake_get_text(url):
        fetched.append(url)
        return _RSS

    monkeypatch.setattr(web_server, "get_text", fake_get_text)
    out = json.loads(web_server.fetch_feed("http://feeds.example.org/f.xml"))

    assert fetched == ["http://feeds.example.org/f.xml"]
    assert out["ok"] is True
    assert out["data"]["feed_title"] == "Example Feed"
    assert out["data"]["items"][0]["title"] == "Agents in production"


def test_search_feeds_fetches_via_shared_http_layer(monkeypatch):
    monkeypatch.setattr(web_server, "get_text", lambda url: _RSS)
    out = json.loads(web_server.search_feeds(
        ["http://feeds.example.org/f.xml"], ["agents"],
    ))

    assert out["ok"] is True
    assert out["data"]["count"] == 1
    assert out["data"]["matches"][0]["title"] == "Agents in production"


def test_stalled_feed_server_times_out_instead_of_hanging(monkeypatch):
    # A server that accepts the connection and never sends a byte. Before the
    # fix, feedparser fetched the URL itself with no timeout and this call
    # never returned.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    conns = []

    def stall():
        try:
            conns.append(srv.accept()[0])
        except OSError:
            pass

    threading.Thread(target=stall, daemon=True).start()
    monkeypatch.setattr(core_http, "_TIMEOUT", 0.5)
    try:
        start = time.monotonic()
        out = json.loads(web_server.fetch_feed(f"http://127.0.0.1:{port}/feed.xml"))
        elapsed = time.monotonic() - start

        assert out["ok"] is False
        assert out["code"] == "upstream"
        assert elapsed < 5, f"feed fetch blocked for {elapsed:.1f}s"
    finally:
        for c in conns:
            c.close()
        srv.close()
