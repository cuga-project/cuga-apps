# Adding a new MCP tool

Goal: ship a new tool on a shared MCP server and have every app that loads
that server pick it up automatically — no per-app code change.

This guide walks the full loop:

1. Decide where the tool lives
2. Implement it
3. Rebuild + restart the server
4. Verify it appears
5. Add a test
6. (Optional) make an existing app call it

We'll use a worked example throughout: a new `slugify(text)` tool on a new
`mcp-text` server. (If you'd rather add to an existing server, skip step "new
server" pieces.)

---

## 1. Pick the right server

Your tool belongs on the existing server whose theme it fits — pure web I/O
goes on `mcp-web`, anything stateless about strings/text goes on `mcp-text`,
host-system reads on `mcp-local`, and so on. Stretch the existing themes
before adding a new server.

If the tool genuinely doesn't fit any current server, see
[Adding a new MCP server](#adding-a-new-mcp-server) at the bottom.

For our example: `slugify` belongs in `mcp-text` (already exists, already
holds stateless text transforms).

## 2. Implement the tool

Open the server file and add a `@mcp.tool()`-decorated function.

```python
# mcp_servers/text/server.py

import re

@mcp.tool()
def slugify(text: str, max_length: int = 60) -> str:
    """Convert a string into a URL-safe slug.

    Lowercases, strips diacritics (best-effort), replaces non-alphanumerics
    with hyphens, collapses runs of hyphens, trims to max_length.

    Args:
        text: Input string.
        max_length: Truncation cap on the output (default 60).
    """
    s = (text or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")[:max_length].strip("-")
    return tool_result({"slug": s, "original_length": len(text or "")})
```

### Rules of thumb

- **Return through the envelope.** Always return either `tool_result(payload)`
  or `tool_error(msg, code=...)` from `mcp_servers._core`. The bridge and the
  test suite both rely on the `{ok, data}` / `{ok: false, error}` shape.
- **Document the args inline.** The docstring is the spec the LLM reads at
  tool-binding time. Be terse and concrete: what each arg means, what shape
  the response has.
- **No shared state.** A tool should be a pure function of its arguments.
  Anything stateful (DB connections, in-memory caches that mutate across
  calls, per-user auth) belongs in an app, not on an MCP server.
- **Defaults that "just work".** Pick conservative defaults so the LLM can
  call the tool with minimal args.

### If you need a new pip dep

Add it to [requirements.mcp.txt](../requirements.mcp.txt) under the section
for the server. If it ships with model files (HuggingFace, faster-whisper-
style), pre-download them in [Dockerfile.mcp](../Dockerfile.mcp) so the first
runtime call doesn't stall on a cold download.

### If your tool needs an API key

Read it from `os.getenv("KEY_NAME")` at call time (not import time — env vars
should be resolvable on a running server, not just at boot). Return a
`tool_error("KEY_NAME not set", code="missing_key")` when missing. Document
the env var in [apps/.env.example](../apps/.env.example).

## 3. Rebuild and restart the server

The MCP image is shared across all 7 servers — they differ only by the
`command:` in [docker-compose.yml](../docker-compose.yml). One rebuild covers
all of them; restart only the affected service.

```bash
docker compose build mcp-text
docker compose up -d mcp-text
```

The apps container caches the tool list at startup, so after adding a tool
you also need to bounce any apps that load this server, so their `load_tools()`
re-runs and picks up the new tool:

```bash
docker compose restart apps
```

(If you skip this, the new tool is reachable via the tool explorer immediately
but won't show up in any app's LLM tool catalog until the next app restart.)

## 4. Verify it landed

The tool explorer auto-discovers everything via MCP `tools/list`, so:

```bash
curl -s http://localhost:28900/api/servers/text/tools | python3 -m json.tool
```

You should see `slugify` in the list. Or open
http://localhost:28900 → mcp-text → look for the new tool with a form.

Smoke-test it via curl:

```bash
curl -s -X POST http://localhost:28900/api/servers/text/tools/slugify/call \
  -H 'Content-Type: application/json' \
  -d '{"args":{"text":"Hello, World! 🌍","max_length":30}}'
```

Expected: a `{"is_error": false, "content":[{"type":"text","text":"{\"ok\":true,\"data\":{\"slug\":\"hello-world\",...}}"}]}`.

## 5. Add a test

Open [tests/test_mcp_tools.py](../tests/test_mcp_tools.py) and add a method to
the matching `TestMcp*` class. The file is the canonical "what's the tool's
contract" document — a future change that breaks the contract will fail this
test.

```python
class TestMcpText:
    # ... existing tests ...

    def test_slugify_basic(self):
        data = _expect_ok(call_mcp_tool("text", "slugify", {
            "text": "Hello, World!",
        }))
        assert data["slug"] == "hello-world"
        assert data["original_length"] == 13

    def test_slugify_max_length(self):
        data = _expect_ok(call_mcp_tool("text", "slugify", {
            "text": "x" * 200, "max_length": 10,
        }))
        assert len(data["slug"]) <= 10
```

Run only your new tests during dev:

```bash
pytest tests/test_mcp_tools.py::TestMcpText::test_slugify_basic -v
pytest -m mcp -k slugify          # pattern match
```

Then run the whole tier to make sure you haven't broken something else:

```bash
make test-mcp
```

Or the full default tier (smoke + mcp + wiring):

```bash
make test
```

## 6. (Optional) Wire it into an app

Apps that already do `load_tools(["text"])` see the new tool automatically on
their next restart — no app code change needed. But you'll often want to
update a system prompt so the LLM knows when to use it.

Find apps that load this server:

```bash
grep -rln 'load_tools.*"text"' apps/ --include="*.py"
```

In the matching app's `main.py`, find the system prompt (usually `_SYSTEM`
or `SYSTEM_INSTRUCTIONS`) and add a line telling the LLM when to call the
new tool. Something like:

```
- Call `slugify` when you need a URL- or filename-safe version of a string.
```

Restart the app:

```bash
docker compose restart apps
```

If you renamed an existing tool (rather than adding a new one), search every
app's prompt for the old name — `pytest -m llm` would catch it eventually but
manual grep is faster.

---

## Adding a new MCP server

Rare, but if your tool genuinely doesn't fit any existing theme, here's the
full checklist.

### Files to add

1. `mcp_servers/<name>/__init__.py` (empty)
2. `mcp_servers/<name>/server.py` — copy [mcp_servers/code/server.py](../mcp_servers/code/server.py)
   as a minimal template (stdlib-only, easiest to start from):

   ```python
   from mcp_servers._core import tool_error, tool_result
   from mcp_servers._core.serve import make_server, run
   from apps._ports import MCP_<NAME>_PORT

   mcp = make_server("mcp-<name>")

   @mcp.tool()
   def first_tool(...) -> str:
       ...
       return tool_result(...)

   if __name__ == "__main__":
       run(mcp, MCP_<NAME>_PORT)
   ```

### Files to update

| File | What to add |
|---|---|
| [apps/_ports.py](../apps/_ports.py) | `MCP_<NAME>_PORT = 29107` (next free) and entry in `MCP_PORTS` dict |
| [requirements.mcp.txt](../requirements.mcp.txt) | any new pip deps |
| [Dockerfile.mcp](../Dockerfile.mcp) | any model pre-downloads |
| [docker-compose.yml](../docker-compose.yml) | new service block (copy `mcp-text`'s; change name + command + port) |
| [apps/launch.py](../apps/launch.py) | append entry to `PROCS` list (mcp kind) |
| [docs/GETTING_STARTED.md](GETTING_STARTED.md) | row in the "What each MCP server exposes" table |

The tool explorer is fully dynamic — it reads `MCP_PORTS` and queries each
server's `tools/list`, so you don't touch the explorer code at all.

### Build + ship

```bash
docker compose build mcp-<name> mcp-tool-explorer    # rebuild explorer too,
                                                       # since its code COPYs apps/_ports.py
docker compose up -d mcp-<name> mcp-tool-explorer
```

### Verify

```bash
curl -s http://localhost:28900/api/servers | python3 -m json.tool
```

Should list 8 servers, all `online: true`. The smoke tests then pin this:

```bash
make test-quick
# 'test_tool_explorer_lists_all_seven_servers' will FAIL — update its
# count to match. That failure is correct and exactly the safety net you
# want; it forces explicit acknowledgment of the new server.
```

Update [tests/test_smoke.py](../tests/test_smoke.py) — the test compares
against `set(MCP_PORTS)`, so just adding the entry to `_ports.py` keeps the
smoke test honest.

---

## Common pitfalls

- **Tool description gets ignored.** The docstring is what the LLM reads.
  If you describe behavior in a code comment instead, the LLM doesn't see it
  and won't know when to call your tool.
- **Forgot `tool_result()`.** Returning a raw string or dict bypasses the
  envelope contract — the bridge will surface garbled responses to the LLM.
- **Long-running tool blocks the server.** FastMCP handles requests
  serially per connection. If your tool takes >30s, consider making it
  return progress markers, or split it into a "kick off" + "poll for
  results" pair.
- **Modified server but still seeing old behaviour.** Did you rebuild
  (`docker compose build mcp-<name>`)? `up -d` alone re-starts but
  doesn't rebuild. Or, did you forget to `restart apps` so apps
  re-introspect the tool list?
