# Testing

cuga-apps ships a real integration test suite — no mocks, no fakes. Every
test hits the live stack started by `docker compose up`. If you change a
tool, an app, or a wire, these tests tell you what broke.

There's also some discussion below of where unit tests fit (spoiler:
deliberately thin — most of the value lives at the integration layer here).

---

## Quick start

```bash
make install-test-deps      # one-time: pip install -r requirements.test.txt
docker compose up -d        # start the stack first
make test                   # ~13s, 120 tests, no LLM cost
```

If a test session-skips with "stack appears down", run `docker compose up -d`
first and wait ~30s for the apps container to finish launching all 23
processes.

## The four tiers

| Tier | Marker | What it tests | Speed | Cost | Default? |
|---|---|---|---|---|---|
| **smoke** | `-m smoke` | Every app + MCP-server endpoint reachable | ~5s | none | ✓ |
| **mcp** | `-m mcp` | Every MCP tool returns a valid envelope when called with real args | ~15s | none | ✓ |
| **wiring** | `-m wiring` | App-side non-LLM REST endpoints work; one stateful round-trip on web_researcher topics | ~5s | none | ✓ |
| **llm** | `-m llm` | Each app's `/ask` produces a non-empty response from the configured LLM | minutes | LLM tokens | opt-in |

```bash
make test-quick   # smoke only — fastest sanity check
make test-mcp     # mcp tier
make test-wiring  # wiring tier
make test         # smoke + mcp + wiring (default)
make test-llm     # llm tier only
make test-all     # everything
```

## What each tier catches

### smoke

- Umbrella UI is serving on 3001
- Tool explorer is serving on 28900 and lists exactly the 7 expected MCP servers
  → if you forget to register a new server in `_ports.py`, this fails immediately
- Every app's port accepts TCP and returns a 2xx/3xx on `/`
- Every MCP server speaks the MCP protocol and returns at least one tool
  → if a server crashes at boot, this fails

If smoke passes, the basic plumbing is intact.

### mcp

One test per MCP tool, calling it with realistic args and validating:

1. The `{ok, data}` envelope shape is correct.
2. Required fields are present in `data`.
3. Bad-input cases return `{ok: false, error, code}` with the expected `code`
   (e.g. `bad_input`, `not_found`, `missing_key`).
4. For tools with multiple modes (chunk_text strategies, encoding choices,
   alert thresholds), each mode is exercised separately.

What this prevents:

- Renaming a tool's argument or return key without updating consumers
- Changing the envelope shape (someone returns raw JSON instead of
  `tool_result(...)`)
- Removing or renaming a tool that an app's prompt still references (the
  matching test fails when its `call_mcp_tool(...)` raises tool-not-found)

Tests skip — never fail — when:
- `TAVILY_API_KEY`, `ALPHA_VANTAGE_API_KEY`, or `OPENTRIPMAP_API_KEY` is
  unset (gated by `@pytest.mark.needs_key("...")`)
- An external service is rate-limiting (Semantic Scholar's `429` is a known flake)

### wiring

For every app, a parametrized test hits its non-LLM REST routes (`/health`,
`/settings`, `/reports`, `/topics`, etc.) and asserts a 2xx with the right
shape (JSON list vs JSON object, fields present).

Plus one stateful round-trip on web_researcher: add a topic → list it →
toggle it → delete it. This exercises the FastAPI route layer and the JSON
persistence layer end-to-end without the LLM. If you break a SQLite
migration or mistype a route, this catches it for ~$0 in tokens.

### llm (opt-in)

Hits each of paper_scout / code_reviewer / wiki_dive / web_researcher's
`/ask` endpoint with a representative prompt and asserts the response is
non-empty. Plus one full pipeline test for drop_summarizer: upload a file
→ wait for `/summaries` to grow → confirm the file got through the
mcp-text → CugaAgent → SQLite chain.

Auto-skips with a clear message if no LLM provider key is configured.

This is the **only** tier that catches "renamed an MCP tool but forgot to
update the system prompt" at runtime — because that bug only manifests
when the LLM picks a tool by name. Run it before merging anything that
touches a system prompt, an MCP tool name, or an MCP tool's input schema.

## Running against a remote stack

The test client just makes HTTP calls — it doesn't know or care that Docker
exists. Set the host:

```bash
CUGA_TEST_HOST=m3bench.example.com make test
```

That works whether the remote stack runs via Docker, via `python launch.py`
on the bare host, or anywhere else the same ports are reachable.

## Layout

```
tests/
├── README.md            short pointer to this doc
├── conftest.py          session guard, helpers, mcp_session fixture
├── test_smoke.py        endpoint reachability — 40 tests
├── test_mcp_tools.py    one TestMcp* class per server — 45 tests
├── test_app_wiring.py   non-LLM REST routes per app + one round-trip — 39 tests
└── test_app_llm.py      opt-in LLM round-trips + drop_summarizer pipeline — 5 tests
```

## Adding tests

### Adding a new MCP tool

Append a test method to the matching `TestMcp*` class in
[tests/test_mcp_tools.py](../tests/test_mcp_tools.py). The pattern is
consistent — copy a sibling test:

```python
class TestMcpText:
    def test_my_new_tool(self):
        data = _expect_ok(call_mcp_tool("text", "my_new_tool", {
            "arg": "value",
        }))
        assert data["expected_field"] == "expected_value"

    def test_my_new_tool_bad_input(self):
        env = call_mcp_tool("text", "my_new_tool", {"arg": ""})
        _expect_error(env, code="bad_input")
```

Helpers `_expect_ok`/`_expect_error` are defined at the top of the file.

### Adding a new app

Just add an entry to `APP_PORTS` in `apps/_ports.py` — the smoke tier
parametrizes over that registry, so your new app is covered automatically.

For wiring coverage, append rows to the `ENDPOINTS` list in
[tests/test_app_wiring.py](../tests/test_app_wiring.py):

```python
ENDPOINTS = [
    # ... existing ...
    ("recipe_finder", "/health",   "json_obj"),
    ("recipe_finder", "/recipes",  "json_list"),
]
```

`json_obj` and `json_list` are the only kinds that validate body shape.
Use `any_2xx` if you don't care about the shape.

### Adding a new test marker

Edit [pytest.ini](../pytest.ini). All markers must be declared there
(`--strict-markers` is set), so a typo fails fast.

## Why no unit tests?

The honest answer: unit tests would mostly assert that Python's `re.split`
or `httpx.get` works. The MCP tools are thin wrappers around external APIs
and stdlib calls — there's not much "logic" to isolate. The integration
suite hits the real `re.split`, the real `httpx.get`, the real Tavily, and
catches end-to-end behavior with no mocks to maintain.

The places where unit tests would actually pay off are:

- `mcp_servers/text/server.py`'s `_chunk_recursive` — non-trivial recursion
  with edge cases. There are integration tests for the three strategies
  but a unit test could enumerate corner cases (empty input, single-char
  input, separators that don't appear in the text) faster.
- `mcp_servers/local/server.py`'s severity classification logic in
  `get_system_metrics_with_alerts` — if this gets more complex, isolate it.

If you decide one of those is worth unit-testing, drop a `tests/unit/`
folder and a `[pytest]` `testpaths` entry. The integration suite is
parametrized; unit tests would just be plain pytest with no special
fixtures needed.

## CI

Not wired yet. To wire it:

```yaml
# .github/workflows/test.yml — sketch
- run: docker compose up -d --wait
- run: pip install -r requirements.test.txt
- run: pytest -m "smoke or mcp or wiring"
- if: success() && env.ANTHROPIC_API_KEY != ''
  run: pytest -m llm
```

Most external-service tests are tagged `@pytest.mark.external` — you can
exclude them in CI with `-m "smoke or mcp or wiring and not external"` if
you want zero-flake runs at the cost of less coverage.

## Common failures and what they mean

| Failure | Likely cause |
|---|---|
| `stack appears down on localhost (UI port 3001 not listening)` | `docker compose up -d` first; wait for apps to finish launching |
| `Tool at index 0 is not a valid LangChain tool. Got list, expected BaseTool` | An app's tool factory wraps `load_tools()`'s return value in an extra `[...]` — see [the youtube_research bug fix](https://github.com/yourrepo/.../) |
| `RuntimeError: There is no current event loop` | Python 3.13 dropped `asyncio.get_event_loop()`'s auto-create behavior — schedule background tasks via `@app.on_event("startup")` instead |
| `name 'get_json' is not defined` | Forgot to import a `_core` helper into a server file |
| Test passes but the app behaves wrong in the browser | Image not rebuilt — `docker compose build && docker compose up -d` |
