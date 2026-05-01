# tests/

Real integration tests against the live cuga-apps stack. **No mocks.**

Full guide: **[docs/TESTING.md](../docs/TESTING.md)**.

## TL;DR

```bash
make install-test-deps      # one-time
docker compose up -d        # start the stack
make test                   # 120 tests, ~13s, no LLM cost
```

## Files

| File | What |
|---|---|
| [conftest.py](conftest.py) | session guard, helpers, MCP client fixture |
| [test_smoke.py](test_smoke.py) | every app + MCP server reachable (40 tests) |
| [test_mcp_tools.py](test_mcp_tools.py) | every MCP tool exercised with real args (45 tests) |
| [test_app_wiring.py](test_app_wiring.py) | non-LLM REST routes per app + a stateful round-trip (39 tests) |
| [test_app_llm.py](test_app_llm.py) | opt-in LLM round-trips and drop_summarizer pipeline (5 tests) |
