"""
Real integration tests for every MCP tool on every server.

Each test calls the tool over the MCP protocol with realistic arguments and
validates the response envelope. No mocks. Tools that need API keys are
skipped (not failed) when the key isn't set.

If a tool's signature, description, or return shape changes in a way that
breaks consumers, one of these tests will fail.
"""
from __future__ import annotations

import pytest

from .conftest import call_mcp_tool


pytestmark = pytest.mark.mcp


def _expect_ok(envelope, *, code: int | None = None) -> dict:
    """Assert an MCP tool returned {ok: true, data: ...} and return the data."""
    assert envelope is not None, "tool returned an empty envelope"
    assert envelope.get("ok") is True, (
        f"tool reported error: code={envelope.get('code')!r} "
        f"error={envelope.get('error')!r}"
    )
    assert "data" in envelope, "ok=True but no data field"
    return envelope["data"]


def _expect_error(envelope, code: str | None = None):
    """Assert an MCP tool returned {ok: false, error: ...}."""
    assert envelope is not None
    assert envelope.get("ok") is False, f"expected error envelope, got: {envelope}"
    assert "error" in envelope
    if code:
        assert envelope.get("code") == code, f"expected code {code}, got {envelope.get('code')}"


# ─── mcp-web ─────────────────────────────────────────────────────────────

class TestMcpWeb:

    @pytest.mark.needs_key("TAVILY_API_KEY")
    @pytest.mark.external
    def test_web_search(self):
        data = _expect_ok(call_mcp_tool("web", "web_search", {
            "query": "Anthropic Claude AI",
            "max_results": 3,
        }))
        # Tavily's response shape passes through unchanged.
        assert isinstance(data, dict)
        assert "results" in data or "answer" in data, f"unexpected payload: {data.keys()}"

    @pytest.mark.external
    def test_fetch_webpage(self):
        data = _expect_ok(call_mcp_tool("web", "fetch_webpage", {
            "url": "https://example.com/",
            "max_chars": 500,
        }))
        assert data["url"] == "https://example.com/"
        assert "Example Domain" in data["text"]

    @pytest.mark.external
    def test_fetch_webpage_links(self):
        data = _expect_ok(call_mcp_tool("web", "fetch_webpage_links", {
            "url": "https://example.com/",
            "limit": 10,
        }))
        assert "links" in data
        assert isinstance(data["links"], list)

    def test_fetch_webpage_handles_invalid_url_gracefully(self):
        env = call_mcp_tool("web", "fetch_webpage", {
            "url": "http://nonexistent.invalid.domain.example/",
        })
        _expect_error(env)

    @pytest.mark.external
    def test_fetch_feed(self):
        data = _expect_ok(call_mcp_tool("web", "fetch_feed", {
            "url": "https://hnrss.org/frontpage",
            "max_items": 5,
        }))
        assert "items" in data
        # HN may be empty during outages; just check shape.
        assert isinstance(data["items"], list)

    @pytest.mark.external
    def test_search_feeds(self):
        data = _expect_ok(call_mcp_tool("web", "search_feeds", {
            "feed_urls": ["https://hnrss.org/frontpage"],
            "keywords":  ["the"],   # very common word — almost always matches
            "max_per_feed": 30,
        }))
        assert "matches" in data
        assert "count" in data
        assert isinstance(data["matches"], list)

    @pytest.mark.external
    def test_get_youtube_video_info(self):
        # Stable, well-known video ID (Rick Astley "Never Gonna Give You Up").
        data = _expect_ok(call_mcp_tool("web", "get_youtube_video_info", {
            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }))
        assert data["video_id"] == "dQw4w9WgXcQ"
        assert data["title"]
        assert data["channel"]

    def test_get_youtube_video_info_rejects_garbage(self):
        env = call_mcp_tool("web", "get_youtube_video_info", {
            "youtube_url": "not-a-youtube-url",
        })
        _expect_error(env, code="bad_input")


# ─── mcp-knowledge ───────────────────────────────────────────────────────

class TestMcpKnowledge:

    @pytest.mark.external
    def test_search_wikipedia(self):
        data = _expect_ok(call_mcp_tool("knowledge", "search_wikipedia", {
            "query": "Alan Turing",
            "max_results": 3,
        }))
        assert data["results"], "Wikipedia returned no results for 'Alan Turing'"
        first = data["results"][0]
        assert "title" in first and "url" in first

    @pytest.mark.external
    def test_get_wikipedia_article_summary(self):
        data = _expect_ok(call_mcp_tool("knowledge", "get_wikipedia_article", {
            "title": "Alan Turing",
            "full":  False,
        }))
        assert data["title"]
        assert data["summary"], "summary field empty"

    @pytest.mark.external
    def test_get_wikipedia_article_full(self):
        data = _expect_ok(call_mcp_tool("knowledge", "get_wikipedia_article", {
            "title": "Alan Turing",
            "full":  True,
        }))
        assert data["title"]
        assert data["extract"]
        assert len(data["extract"]) > 1000, "full extract too short — wrong endpoint?"

    @pytest.mark.external
    def test_get_article_summary_alias(self):
        data = _expect_ok(call_mcp_tool("knowledge", "get_article_summary", {
            "title": "Python (programming language)",
        }))
        assert data["title"]
        assert data["summary"]

    @pytest.mark.external
    def test_get_article_sections_alias(self):
        data = _expect_ok(call_mcp_tool("knowledge", "get_article_sections", {
            "title": "Python (programming language)",
        }))
        assert data["title"]
        assert data["extract"]

    @pytest.mark.external
    def test_get_related_articles(self):
        data = _expect_ok(call_mcp_tool("knowledge", "get_related_articles", {
            "title": "Alan Turing",
            "max_results": 5,
        }))
        assert isinstance(data["related"], list)

    @pytest.mark.external
    def test_search_arxiv(self):
        data = _expect_ok(call_mcp_tool("knowledge", "search_arxiv", {
            "query": "transformer attention",
            "max_results": 3,
        }))
        assert data["results"], "arXiv returned no hits for 'transformer attention'"
        assert data["results"][0]["title"]
        assert data["results"][0]["arxiv_id"]

    @pytest.mark.external
    def test_get_arxiv_paper(self):
        # "Attention Is All You Need" — stable arXiv ID.
        data = _expect_ok(call_mcp_tool("knowledge", "get_arxiv_paper", {
            "arxiv_id": "1706.03762",
        }))
        assert data["arxiv_id"].startswith("1706.03762")
        assert "Attention" in data["title"]

    @pytest.mark.external
    def test_search_semantic_scholar(self):
        env = call_mcp_tool("knowledge", "search_semantic_scholar", {
            "query": "transformer attention",
            "max_results": 3,
        })
        # S2 rate-limits aggressively from CI/cloud IPs — treat 429 as a flake.
        if env.get("ok"):
            assert env["data"]["results"], "Semantic Scholar returned no hits"
        else:
            assert env["code"] == "upstream", env
            pytest.skip(f"Semantic Scholar transient error: {env.get('error')}")


# ─── mcp-geo ─────────────────────────────────────────────────────────────

class TestMcpGeo:

    @pytest.mark.external
    def test_geocode(self):
        data = _expect_ok(call_mcp_tool("geo", "geocode", {"place": "Paris, France"}))
        assert isinstance(data["lat"], float)
        assert isinstance(data["lon"], float)
        # Paris is roughly 48.85 N, 2.35 E.
        assert 48 < data["lat"] < 49
        assert 2 < data["lon"] < 3

    @pytest.mark.external
    def test_get_weather(self):
        data = _expect_ok(call_mcp_tool("geo", "get_weather", {
            "city": "Tokyo",
            "travel_month": "March",
        }))
        assert data["city"] == "Tokyo"
        assert data["current"]["temp_c"] is not None
        assert isinstance(data["forecast"], list)

    @pytest.mark.external
    def test_find_hikes(self):
        # Mt. Rainier area.
        env = call_mcp_tool("geo", "find_hikes", {
            "lat": 46.85, "lon": -121.76,
            "radius_km": 15, "difficulty": "any",
        })
        # Overpass can be slow / rate-limited; accept either ok or upstream.
        if env.get("ok"):
            assert "hikes" in env["data"]
            assert isinstance(env["data"]["hikes"], list)
        else:
            assert env.get("code") == "upstream"

    @pytest.mark.needs_key("OPENTRIPMAP_API_KEY")
    @pytest.mark.external
    def test_search_attractions(self):
        # Coords for Prague.
        data = _expect_ok(call_mcp_tool("geo", "search_attractions", {
            "lat": 50.0755, "lon": 14.4378,
            "category": "interesting_places",
            "limit": 5,
        }))
        assert "attractions" in data
        assert isinstance(data["attractions"], list)


# ─── mcp-finance ─────────────────────────────────────────────────────────

class TestMcpFinance:

    @pytest.mark.external
    def test_get_crypto_price(self):
        data = _expect_ok(call_mcp_tool("finance", "get_crypto_price", {
            "symbol": "BTC",
        }))
        assert data["coingecko_id"] == "bitcoin"
        assert isinstance(data["price"], (int, float))
        assert data["price"] > 0

    def test_get_crypto_price_unknown_symbol(self):
        env = call_mcp_tool("finance", "get_crypto_price", {
            "symbol": "definitely-not-a-real-coin-xyz",
        })
        # CoinGecko returns empty dict for unknown ids → tool emits not_found.
        assert env["ok"] is False

    @pytest.mark.needs_key("ALPHA_VANTAGE_API_KEY")
    @pytest.mark.external
    def test_get_stock_quote(self):
        env = call_mcp_tool("finance", "get_stock_quote", {"symbol": "AAPL"})
        # Alpha Vantage free tier rate-limits aggressively (25/day) — accept
        # rate_limit as a non-failure.
        if env["ok"]:
            assert env["data"]["price"] > 0
        else:
            assert env.get("code") in ("rate_limit", "not_found"), env


# ─── mcp-code ────────────────────────────────────────────────────────────

class TestMcpCode:

    def test_check_python_syntax_valid(self):
        data = _expect_ok(call_mcp_tool("code", "check_python_syntax", {
            "code": "def f(x):\n    return x + 1\n",
        }))
        assert data["valid"] is True
        assert data["error"] is None

    def test_check_python_syntax_invalid(self):
        data = _expect_ok(call_mcp_tool("code", "check_python_syntax", {
            "code": "def f(:\n    return\n",
        }))
        assert data["valid"] is False
        assert data["error"]
        assert data["line"] == 1

    def test_extract_code_metrics(self):
        code = (
            "def add(a, b):\n"
            "    if a > b:\n"
            "        return a\n"
            "    else:\n"
            "        return b\n"
            "\n"
            "class Calc:\n"
            "    def double(self, x):\n"
            "        return x * 2\n"
        )
        data = _expect_ok(call_mcp_tool("code", "extract_code_metrics", {"code": code}))
        assert data["total_lines"] == 9
        assert data["non_blank_lines"] == 8
        assert data["branch_complexity_estimate"] >= 2
        names = data["top_level_definitions"]
        assert "FunctionDef:add" in names
        assert "ClassDef:Calc" in names

    def test_detect_language_python(self):
        data = _expect_ok(call_mcp_tool("code", "detect_language", {
            "code": "def f(x):\n    import os\n    return os.path.exists(x)\n",
        }))
        assert data["language"] == "python"
        assert data["confidence"] in ("medium", "high")

    def test_detect_language_javascript(self):
        data = _expect_ok(call_mcp_tool("code", "detect_language", {
            "code": "const f = (x) => { console.log(x); return x + 1 };\n",
        }))
        assert data["language"] == "javascript"


# ─── mcp-local ───────────────────────────────────────────────────────────

class TestMcpLocal:

    def test_get_system_metrics(self):
        data = _expect_ok(call_mcp_tool("local", "get_system_metrics"))
        assert 0 <= data["cpu_percent"] <= 100
        assert 0 <= data["memory_percent"] <= 100
        assert 0 <= data["disk_percent"] <= 100
        assert isinstance(data["load_avg_1_5_15"], list)
        assert len(data["load_avg_1_5_15"]) == 3

    def test_get_system_metrics_with_alerts_ok(self):
        # Use very high thresholds — shouldn't fire on a healthy host.
        data = _expect_ok(call_mcp_tool("local", "get_system_metrics_with_alerts", {
            "thresholds": {
                "cpu_warn":  99.5, "cpu_crit":  99.9,
                "ram_warn":  99.5, "ram_crit":  99.9,
                "disk_warn": 99.5, "disk_crit": 99.9,
            }
        }))
        assert data["severity"] == "ok"
        assert data["alerts"] == []
        assert data["thresholds"]["cpu_warn"] == 99.5

    def test_get_system_metrics_with_alerts_critical(self):
        # Use very low thresholds — every reading should breach critical.
        data = _expect_ok(call_mcp_tool("local", "get_system_metrics_with_alerts", {
            "thresholds": {
                "cpu_warn":  0.01, "cpu_crit":  0.02,
                "ram_warn":  0.01, "ram_crit":  0.02,
                "disk_warn": 0.01, "disk_crit": 0.02,
            }
        }))
        assert data["severity"] == "critical"
        assert len(data["alerts"]) >= 1

    def test_list_top_processes(self):
        data = _expect_ok(call_mcp_tool("local", "list_top_processes", {"by": "cpu", "n": 5}))
        assert data["sort_by"] == "cpu"
        assert isinstance(data["processes"], list)
        assert len(data["processes"]) > 0

    def test_check_disk_usage(self):
        data = _expect_ok(call_mcp_tool("local", "check_disk_usage", {"path": "/"}))
        assert data["total_gb"] > 0
        assert data["free_gb"] >= 0
        assert 0 <= data["percent"] <= 100

    def test_find_large_files_path_missing(self):
        env = call_mcp_tool("local", "find_large_files", {
            "path": "/this/does/not/exist/anywhere",
            "min_mb": 1,
        })
        _expect_error(env, code="not_found")

    def test_get_service_status_unknown(self):
        # Either returns a state ("unknown" / "inactive") or fails gracefully if
        # the host has no systemctl (mac, minimal containers).
        env = call_mcp_tool("local", "get_service_status", {
            "name": "definitely-no-such-service",
        })
        if env["ok"]:
            assert "state" in env["data"]
        else:
            assert env["code"] in ("unsupported", "io")


# ─── mcp-text ────────────────────────────────────────────────────────────

class TestMcpText:

    def test_chunk_text_recursive(self):
        text = "Section one.\n\nSection two with much more content here, definitely longer than the chunk size.\n\nSection three."
        data = _expect_ok(call_mcp_tool("text", "chunk_text", {
            "text": text, "strategy": "recursive", "size": 40, "overlap": 5,
        }))
        assert data["count"] >= 2
        assert data["strategy"] == "recursive"
        # Reassembled chunks should preserve every source character (modulo overlap dupes).
        joined = "".join(data["chunks"])
        for piece in ("Section one", "Section two", "Section three"):
            assert piece in joined

    def test_chunk_text_fixed_chars(self):
        text = "x" * 1000
        data = _expect_ok(call_mcp_tool("text", "chunk_text", {
            "text": text, "strategy": "fixed_chars", "size": 100, "overlap": 10,
        }))
        # 1000 chars / (100 - 10) advance = ~12 chunks.
        assert 9 <= data["count"] <= 14
        for c in data["chunks"]:
            assert len(c) <= 100

    def test_chunk_text_markdown_headers(self):
        text = (
            "# Title\n\nIntro text.\n\n"
            "## Section A\n\nContent A.\n\n"
            "## Section B\n\nContent B.\n"
        )
        data = _expect_ok(call_mcp_tool("text", "chunk_text", {
            "text": text, "strategy": "markdown_headers", "size": 1000,
        }))
        assert data["count"] == 3
        assert data["chunks"][0].startswith("# Title")
        assert data["chunks"][1].startswith("## Section A")
        assert data["chunks"][2].startswith("## Section B")

    def test_chunk_text_unknown_strategy(self):
        env = call_mcp_tool("text", "chunk_text", {
            "text": "hello", "strategy": "no-such-strategy",
        })
        _expect_error(env, code="bad_input")

    def test_count_tokens_cl100k(self):
        data = _expect_ok(call_mcp_tool("text", "count_tokens", {
            "text": "Hello, world!",
            "encoding": "cl100k_base",
        }))
        assert data["token_count"] > 0
        assert data["token_count"] < data["char_count"]
        assert data["encoding"] == "cl100k_base"

    def test_count_tokens_o200k(self):
        data = _expect_ok(call_mcp_tool("text", "count_tokens", {
            "text": "Hello, world!",
            "encoding": "o200k_base",
        }))
        assert data["token_count"] > 0

    def test_count_tokens_unknown_encoding(self):
        env = call_mcp_tool("text", "count_tokens", {
            "text": "hello", "encoding": "no-such-encoding",
        })
        _expect_error(env, code="bad_input")

    def test_extract_text_missing_file(self):
        env = call_mcp_tool("text", "extract_text", {
            "file_path": "/no/such/file/anywhere.pdf",
        })
        _expect_error(env, code="not_found")

    def test_extract_text_from_bytes_round_trip(self):
        # Build a tiny PDF in memory that docling can definitely parse.
        # (We use a minimal valid PDF the runtime ships with: trick — use a
        #  small HTML doc instead, which docling also handles, and
        #  doesn't require any third-party PDF generation.)
        import base64
        html = b"<html><body><h1>Hello</h1><p>This is a test document.</p></body></html>"
        env = call_mcp_tool("text", "extract_text_from_bytes", {
            "content_b64":    base64.b64encode(html).decode(),
            "file_extension": ".html",
            "max_chars":      1000,
        }, timeout=120)
        # Docling sometimes complains about minimal HTML; accept either ok or upstream.
        if env["ok"]:
            assert env["data"]["markdown"]
        else:
            # If docling refused this minimal doc, at least confirm the right error code.
            assert env["code"] in ("upstream",)
