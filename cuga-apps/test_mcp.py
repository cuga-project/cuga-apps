#!/usr/bin/env python3
"""
test_mcp.py — smoke-test every tool on every cuga-apps MCP server.

For each server, opens ONE streamable-HTTP session, lists tools (verifies the
handshake), then calls every advertised tool with realistic args. Reports
per-tool pass/fail/warn with timing.

Usage:
    python test_mcp.py                              # local (default)
    python test_mcp.py --target ce                  # IBM Cloud Code Engine
    python test_mcp.py --target ce --parallel       # parallel across servers
    python test_mcp.py --names knowledge code       # subset of servers
    python test_mcp.py --timeout 90                 # bump timeout

URL resolution:
    --target local : http://localhost:<port>/mcp from the local port registry
    --target ce    : built from CE_PROJECT_HASH + CE_REGION constants below
                     (no `ibmcloud` shell-out — change those two strings if
                     you redeploy in a different CE project)
    Per-server override: env var MCP_<NAME>_URL wins over both.

What "PASS" means:
    The tool is advertised, dispatches without crashing, and returns either
    ok=true OR a structured ok=false envelope with one of these codes:
      - missing_key   (server up, just lacking a third-party API key)
      - missing_dep   (server up, just missing an optional Python dep)
      - upstream      (server up, third-party API flaked)
      - any code listed in the probe's `accept_codes`
    Otherwise FAIL — the test verifies our infra, not third-party APIs.

Exit code: 0 if every probed tool dispatched cleanly, 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any


# ── CE project hardcodes ─────────────────────────────────────────────────
# CE app URLs follow the pattern
#   https://<app-name>.<project-hash>.<region>.codeengine.appdomain.cloud
# The hash + region are stable for the life of the project, so we hardcode
# them. Change these two strings if you redeploy in a different project or
# region.
CE_PROJECT_HASH = "1gxwxi8kos9y"
CE_REGION       = "us-east"


# ── MCP server registry ─────────────────────────────────────────────────
MCPS: dict[str, dict[str, Any]] = {
    "web":       {"port": 29100, "ce_app": "cuga-apps-mcp-web"},
    "knowledge": {"port": 29101, "ce_app": "cuga-apps-mcp-knowledge"},
    "geo":       {"port": 29102, "ce_app": "cuga-apps-mcp-geo"},
    "finance":   {"port": 29103, "ce_app": "cuga-apps-mcp-finance"},
    "code":      {"port": 29104, "ce_app": "cuga-apps-mcp-code"},
    "local":     {"port": 29105, "ce_app": "cuga-apps-mcp-local"},
    "text":      {"port": 29106, "ce_app": "cuga-apps-mcp-text"},
}


# ── Probes ──────────────────────────────────────────────────────────────
# Per server: a list of (tool_name, args) or (tool_name, args, [accept_codes]).
# Args match the actual signatures in mcp_servers/<name>/server.py — keep in
# sync if those change. accept_codes are extra error codes to treat as PASS
# beyond the always-safe set (missing_key, missing_dep, upstream).
Probe = tuple  # (str, dict) | (str, dict, list[str])

PROBES: dict[str, list[Probe]] = {
    "web": [
        ("web_search",             {"query": "ibm cloud code engine", "max_results": 3}),
        ("fetch_webpage",          {"url": "https://example.com", "max_chars": 2000}),
        ("fetch_webpage_links",    {"url": "https://example.com", "limit": 5}),
        ("fetch_feed",             {"url": "https://hnrss.org/frontpage", "max_items": 3}),
        ("search_feeds",           {"feed_urls": ["https://hnrss.org/frontpage"],
                                    "keywords": ["the"], "max_per_feed": 3}),
        ("get_youtube_video_info", {"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}),
        ("get_youtube_transcript", {"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                                    "max_words": 200}),
    ],
    "knowledge": [
        ("search_wikipedia",        {"query": "IBM Cloud", "max_results": 3}),
        ("get_wikipedia_article",   {"title": "IBM Cloud", "full": False}),
        ("get_article_summary",     {"title": "IBM Cloud"}),
        ("get_article_sections",    {"title": "IBM Cloud"}),
        ("get_related_articles",    {"title": "IBM Cloud", "max_results": 3}),
        ("search_arxiv",            {"query": "transformer", "max_results": 3}),
        ("get_arxiv_paper",         {"arxiv_id": "1706.03762"}),  # Attention Is All You Need
        ("search_semantic_scholar", {"query": "graph neural networks", "max_results": 3}),
        ("get_paper_references",    {"paper_id": "1706.03762"}),
    ],
    "geo": [
        ("geocode",                 {"place": "Yosemite National Park"}),
        ("find_hikes",              {"lat": 37.8651, "lon": -119.5383, "radius_km": 10}),
        # search_attractions needs OPENTRIPMAP_API_KEY → typically missing_key on CE
        ("search_attractions",      {"lat": 37.8651, "lon": -119.5383, "limit": 5}),
        ("get_weather",             {"city": "Yosemite, CA"}),
    ],
    "finance": [
        ("get_crypto_price",        {"symbol": "BTC"}),
        # get_stock_quote takes an optional api_key arg; without it expect missing_key.
        ("get_stock_quote",         {"symbol": "IBM"}),
    ],
    "code": [
        ("check_python_syntax",     {"code": "print('hello mcp')\n"}),
        ("extract_code_metrics",    {"code": "def f():\n    return 1\n\nclass A: pass\n"}),
        ("detect_language",         {"code": "function foo() { return 1; }"}),
    ],
    "local": [
        ("get_system_metrics",             {}),
        ("get_system_metrics_with_alerts", {}),
        ("list_top_processes",             {"by": "cpu", "n": 5}),
        ("check_disk_usage",               {"path": "/"}),
        ("find_large_files",               {"path": "/tmp", "min_mb": 1, "max_results": 5}),
        ("get_service_status",             {"name": "sshd"},  ["not_found"]),
        # Probe with a deliberate bogus path; expect not_found.
        ("transcribe_audio",               {"file_path": "/nonexistent.wav"},
                                            ["not_found", "bad_input"]),
    ],
    "text": [
        ("chunk_text",              {"text": "lorem ipsum dolor sit amet " * 50, "size": 100}),
        ("count_tokens",            {"text": "Hello, MCP world."}),
        # extract_text needs a real file; deliberate bogus path → not_found.
        ("extract_text",            {"file_path": "/nonexistent.pdf"},  ["not_found"]),
        # Tiny base64-encoded "Hello world\n" as a .txt — works without docling
        # if the server short-circuits .txt; otherwise treated as missing_dep.
        ("extract_text_from_bytes", {"content_b64": "SGVsbG8gd29ybGQK", "file_extension": ".txt"}),
    ],
}

# Error codes always treated as PASS-with-warning (server up, just not
# fully configured).
SAFE_ERROR_CODES = {"missing_key", "missing_dep", "upstream"}


# ── Pretty-print helpers ────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty() and not os.getenv("NO_COLOR")
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s
GREEN = lambda s: _c("32", s)  # noqa: E731
RED   = lambda s: _c("31", s)  # noqa: E731
YEL   = lambda s: _c("33", s)  # noqa: E731
BOLD  = lambda s: _c("1", s)   # noqa: E731
DIM   = lambda s: _c("2", s)   # noqa: E731


# ── URL resolution ──────────────────────────────────────────────────────
def resolve_url(name: str, target: str) -> str | None:
    env_override = os.getenv(f"MCP_{name.upper()}_URL")
    if env_override:
        return env_override
    if target == "local":
        return f"http://localhost:{MCPS[name]['port']}/mcp"
    if target == "ce":
        app = MCPS[name]["ce_app"]
        return f"https://{app}.{CE_PROJECT_HASH}.{CE_REGION}.codeengine.appdomain.cloud/mcp"
    raise ValueError(f"unknown target: {target!r}")


# ── Probe one tool ──────────────────────────────────────────────────────
def _classify_probe_result(payload: Any, accept_codes: list[str]) -> dict[str, Any]:
    """Inspect a parsed cuga tool response. Return {status, summary}.

    status ∈ {"pass", "warn", "fail"}.
    """
    if isinstance(payload, dict) and "ok" in payload:
        if payload["ok"]:
            data_preview = json.dumps(payload.get("data", ""), default=str)[:80]
            return {"status": "pass", "summary": data_preview}
        code = payload.get("code", "") or ""
        err = (payload.get("error", "") or "")[:90]
        if code in SAFE_ERROR_CODES or code in accept_codes:
            return {"status": "warn", "summary": f"code={code}: {err}"}
        return {"status": "fail", "summary": f"code={code}: {err}"}
    # Non-envelope payload — accept as pass since the tool dispatched.
    return {"status": "pass", "summary": str(payload)[:80]}


async def probe_one_tool(session, probe: Probe) -> dict[str, Any]:
    tool_name = probe[0]
    args = probe[1]
    accept_codes = list(probe[2]) if len(probe) > 2 else []

    t0 = time.monotonic()
    try:
        res = await session.call_tool(tool_name, args)
    except Exception as exc:
        return {"tool": tool_name, "status": "fail",
                "elapsed": time.monotonic() - t0,
                "summary": f"{type(exc).__name__}: {exc}"}

    elapsed = time.monotonic() - t0
    if res.isError:
        return {"tool": tool_name, "status": "fail", "elapsed": elapsed,
                "summary": "isError=True"}

    text = "".join(getattr(b, "text", "") for b in (res.content or []))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = text

    classified = _classify_probe_result(payload, accept_codes)
    return {"tool": tool_name, "elapsed": elapsed, **classified}


# ── Probe one server ────────────────────────────────────────────────────
async def probe_server(name: str, url: str) -> dict[str, Any]:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    server_t0 = time.monotonic()
    async with streamablehttp_client(url) as (read, write, _close):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_listing = await session.list_tools()
            advertised = {t.name for t in tools_listing.tools}

            results = []
            for probe in PROBES.get(name, []):
                if probe[0] not in advertised:
                    results.append({"tool": probe[0], "status": "fail",
                                    "summary": "not advertised by server"})
                    continue
                results.append(await probe_one_tool(session, probe))

            return {
                "reachable": True,
                "advertised_count": len(advertised),
                "advertised": sorted(advertised),
                "results": results,
                "elapsed": time.monotonic() - server_t0,
            }


async def probe_server_with_timeout(name: str, url: str | None, timeout: int) -> dict[str, Any]:
    if not url:
        return {"reachable": False, "error": "no URL resolved (server not deployed?)",
                "results": []}
    try:
        return await asyncio.wait_for(probe_server(name, url), timeout)
    except asyncio.TimeoutError:
        return {"reachable": False,
                "error": f"timeout after {timeout}s (CE cold start? bump --timeout)",
                "results": []}
    except Exception as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}",
                "results": []}


# ── Output ──────────────────────────────────────────────────────────────
def _status_label(status: str) -> str:
    if status == "pass": return GREEN("PASS")
    if status == "warn": return YEL("WARN")
    return RED("FAIL")


def print_server_section(name: str, url: str | None, server_result: dict[str, Any]) -> None:
    print()
    head = BOLD(f"═══ {name} ═══")
    if url:
        print(f"{head}   {DIM(url)}")
    else:
        print(head)

    if not server_result.get("reachable"):
        print(f"  {RED('UNREACHABLE')}  {server_result.get('error', '?')}")
        return

    advertised = server_result.get("advertised_count", 0)
    untested = sorted(set(server_result["advertised"]) -
                      {r["tool"] for r in server_result["results"]})
    print(DIM(f"  {advertised} tools advertised, {len(server_result['results'])} probed"
              + (f", untested: {untested}" if untested else "")))

    for r in server_result["results"]:
        elapsed = r.get("elapsed")
        e = f"{elapsed:5.2f}s" if elapsed is not None else "  ---"
        print(f"  {r['tool']:32s}  {_status_label(r['status'])}  {e}  "
              f"{DIM(r.get('summary', ''))}")


# ── Main ────────────────────────────────────────────────────────────────
async def main_async(args) -> int:
    names = args.names or list(MCPS)
    for n in names:
        if n not in MCPS:
            print(RED(f"unknown server: {n}. Known: {list(MCPS)}"), file=sys.stderr)
            return 2

    print()
    print(BOLD(f"  Testing {len(names)} MCP server(s) against target={args.target}  "
               f"(timeout={args.timeout}s, parallel={args.parallel})"))

    urls = {n: resolve_url(n, args.target) for n in names}

    if args.parallel:
        tasks = {n: asyncio.create_task(probe_server_with_timeout(n, urls[n], args.timeout))
                 for n in names}
        server_results = {n: await tasks[n] for n in names}
    else:
        server_results = {}
        for n in names:
            server_results[n] = await probe_server_with_timeout(n, urls[n], args.timeout)

    for n in names:
        print_server_section(n, urls[n], server_results[n])

    # ── Summary ────────────────────────────────────────────────────────
    total_tools = 0
    counts = {"pass": 0, "warn": 0, "fail": 0}
    unreachable = 0
    for n in names:
        sr = server_results[n]
        if not sr.get("reachable"):
            unreachable += 1
            continue
        for r in sr["results"]:
            total_tools += 1
            counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print(BOLD("  Summary"))
    line = (
        f"  {counts['pass']} pass · "
        f"{YEL(str(counts['warn']) + ' warn')} · "
        f"{RED(str(counts['fail']) + ' fail')}  "
        f"({total_tools} tool probes across {len(names) - unreachable}/{len(names)} reachable servers)"
    )
    print(line)

    print()
    return 0 if (counts["fail"] == 0 and unreachable == 0) else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test every tool on every cuga-apps MCP server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--target", choices=["local", "ce"], default="local",
                        help="where to test (default: local)")
    parser.add_argument("--names", nargs="*", default=None,
                        help=f"servers to test (default: all). Choices: {list(MCPS)}")
    parser.add_argument("--timeout", type=int, default=120,
                        help="per-server timeout in seconds (default: 120)")
    parser.add_argument("--parallel", action="store_true",
                        help="probe servers in parallel (faster, output is interleaved-then-grouped)")
    args = parser.parse_args()

    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
