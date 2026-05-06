# Ouroboros — CUGA finds its next client

A multi-agent CUGA app for **autonomous local-business lead generation**.
Type a location and (optionally) a category — `find restaurants in
pleasantville NY`, `salons in brooklyn that need appointment booking` —
and the app produces a ranked board of independent businesses that would
benefit from a CUGA-powered conversational agent, with tailored pitches
and (for the top 3) drafted cold emails.

Built on `feat/skills-support` of the CUGA SDK. Uses
**CugaSupervisor + 7 specialist CugaAgents + Skills + Policies + MCP**.

For the design (diagram, agent fact sheet, cascade flow, SDK quirks):
see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Install

### Prerequisites

- macOS (Apple Silicon or Intel) — Linux likely works; Windows untested.
- **Python 3.12 from Homebrew** — `python.org`'s 3.11 / 3.12 installer
  ships without `enable_load_extension`, which `sqlite-vec` (CUGA's
  policy embedding store) requires. Install via `brew install python@3.12`.
- A working **RITS API key** with access to `gpt-oss-120b` (the only
  combination we've verified end-to-end on this branch).

### One-time setup

```bash
cd /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-apps/apps/ouroboros

# 1. Fresh venv with brew Python 3.12
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip

# 2. CUGA SDK from the skills-branch (editable path install)
.venv/bin/pip install -e /Users/anu/Documents/GitHub/cuga-agent-skills-branch

# 3. App-level deps (CUGA pulls most of these transitively, but be
#    explicit so a future `pip install -r requirements.txt` works
#    standalone if cuga is already present)
.venv/bin/pip install langchain-anthropic 'fastapi>=0.110' \
    'uvicorn[standard]>=0.27' 'pydantic>=2.0' 'httpx>=0.27' \
    langchain-mcp-adapters sqlite-vec
```

### Verify

```bash
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect(':memory:')
c.enable_load_extension(True)   # must not raise
import sqlite_vec; sqlite_vec.load(c)
from cuga.sdk import CugaAgent, CugaSupervisor
print('OK — venv ready')
"
```

If `enable_load_extension` raises `AttributeError`, your Python build
lacks loadable-extension support. Rebuild the venv with brew's
python@3.12.

---

## Configure

Set these env vars before each run (or put them in `.profile`):

| Var | Required | Notes |
|---|---|---|
| `LLM_PROVIDER`         | yes | `rits` (only verified value) |
| `LLM_MODEL`            | yes | `gpt-oss-120b` |
| `AGENT_SETTING_CONFIG` | yes | `settings.rits.toml` — must be set BEFORE the first cuga import (we set a default at module top, so just keep it consistent) |
| `RITS_API_KEY`         | yes | your RITS key |
| `CUGA_TARGET`          | no  | defaults to `ce` in `main.py`; routes MCP `web_search` etc. to the hosted Code Engine endpoints |

Other providers (Anthropic, OpenAI, watsonx) currently won't work —
CUGA's `LLMManager` doesn't have an `anthropic` platform branch, and
internal sub-models read the TOML directly. To add Anthropic support
you'd need to monkey-patch `LLMManager.get_model`. See
[ARCHITECTURE.md §SDK quirks](ARCHITECTURE.md#sdk-quirks-worth-knowing-collected-the-hard-way).

---

## Run

### The HTTP server

```bash
cd /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-apps/apps/ouroboros

# stop any stale instance
lsof -ti TCP:28822 -sTCP:LISTEN | xargs kill 2>/dev/null

# start
.venv/bin/python main.py --port 28822
```

Then open <http://127.0.0.1:28822> and try one of these:

- `find restaurants in pleasantville NY`
- `salons in brooklyn — appointment booking pitch`
- `independent hotels in lisbon — concierge agent angle`
- `clinics in austin — patient FAQ + intake`
- `real estate offices in san mateo — lead capture pitch`

A request takes 1–3 minutes (scout + 5 specialist sweeps × 3 candidates
+ writer = ~15 LLM round-trips). The chat panel updates when the writer
returns; the right panel polls `/session/<thread_id>` every 8s and
re-renders.

### The diagnostic (dumps the supervisor's full trace)

When something goes wrong in the chat, run this to see exactly which
specialist got called, what each one returned, and where the cascade
broke:

```bash
.venv/bin/python diag.py "find restaurants in pleasantville NY"
```

Outputs:
- `/tmp/ouroboros_diag.txt` — the supervisor's chat trace + final answer
- `/tmp/ouroboros_diag.log` — full debug log (tracing, policies, etc.)

The text file is the first thing to look at when debugging. It shows:
- exactly what code blocks the supervisor's planner generated
- what each specialist returned
- whether the writer received the consolidated context
- whether the JSON parsed into a leads board

---

## Endpoints

| Method | Path                       | Purpose                                                                     |
| ------ | -------------------------- | --------------------------------------------------------------------------- |
| GET    | `/`                        | Dark-themed UI                                                              |
| GET    | `/health`                  | `{"ok": true}` — supervisor not yet built (cheap health check)              |
| GET    | `/specialists`             | Lazy-build supervisor and list 7 specialists + descriptions                 |
| POST   | `/ask`                     | `{question, thread_id}` → `{answer, thread_id}` (the long one — 1–3 min)    |
| GET    | `/session/{thread_id}`     | Server-held session for that thread (location, focus, latest leads, etc.)   |

---

## Repo layout

```
apps/ouroboros/
├── main.py                  FastAPI + supervisor build + policy attach + executor patch
├── specialists.py           7 factories: each loads one skill into a CugaAgent
├── ui.py                    dark two-panel UI
├── diag.py                  one-shot end-to-end diagnostic
├── README.md                this file — install, run, troubleshoot
├── ARCHITECTURE.md          design reference: diagram, agents, cascade, quirks
├── requirements.txt         dependency hints (cuga is path-installed separately)
└── skills/
    ├── scout/                  geocode + Overpass / OSM
    ├── site_auditor/           capability + freshness signal classifier
    ├── voice_of_customer/      review-snippet friction mining
    ├── person_finder/          owner search + email pattern guesses
    ├── stack_scanner/          third-party widget fingerprint
    ├── revenue_estimator/      size signals → coarse ARR band
    └── pitch_email_writer/     synthesis (no tools)
```

After first run you'll see seven `.cuga_<specialist>/` folders — those
are CUGA's per-agent filesystem-sync of attached policies. Safe to
delete; they get regenerated.

---

## Adding an 8th specialist

1. `mkdir skills/<new_name>/` and write a `SKILL.md` (frontmatter `name`,
   `description`, body) + `tools.py` exporting `TOOLS = [...]`.
2. Add a `make_<new_name>(model)` factory in `specialists.py` (one-liner
   wrapping `_make_agent(_load_skill("<new_name>"), model=model)`).
3. Add it to `SPECIALIST_NAMES` and the `make_all()` dict.
4. Restart. The supervisor's planner sees the new
   `delegate_to_<new_name>` tool automatically.
5. To make it run on every `/ask`, add a sweep to phase 2 of
   `_TASK_PRELUDE` in `main.py`.

To promote a skill to a system-global so other CUGA apps on the machine
can discover it, copy its folder to `~/.config/agents/skills/`.

---

## Troubleshooting

We hit a lot of bugs building this app. Each one is documented here so
you can recognize the symptom fast.

### "Empty board / no leads"

**Symptom**: `/ask` returns a JSON board with `"leads": []` or with all
leads having `evidence: []` and `deep_dive: false`.

**Common causes**:

1. **`AGENT_SETTING_CONFIG` not set before cuga import** — internal
   sub-LLMs default to OpenAI gpt-4o with no key, fail silently inside
   specialists, scout returns an empty/partial response. Check
   `main.py` sets `AGENT_SETTING_CONFIG=settings.rits.toml` at module
   top, BEFORE any `from cuga…` import.
2. **Triple-backticks in the prelude** — CUGA's code extractor uses
   non-greedy `r'```python(.*?)```'`, so any `` ``` `` inside a regex or
   string literal closes the fence early → block silently dropped → "no
   code, final answer" misclassification → cascade short-circuits. The
   prelude must stay backtick-free.
3. **Scout returns truncated JSON** — RITS prod defaults to ~1024
   max_tokens if not set. `RITSChatModel.max_tokens=16000` is set in
   `_llm.py`. If you see `Items: 222` for `scout_result` in the diag,
   this is the cause.
4. **Planner skipped the deep-dive sweeps** — phase 2 of the prelude
   prescribes 5 sweeps; sometimes the planner runs only 1–2 and jumps
   to the writer. The writer still produces a board but `deep_dive=false`
   and `evidence=[]`. Run `diag.py` and inspect — see which specialists
   actually got called.

### "supervisor terminates after one block"

**Symptom**: chat answer is just scout's raw OSM list as a markdown
table, no JSON.

**Cause**: prior versions used too-short or too-narrative preludes that
let the planner judge "scout was enough, return". The current prelude
is prescriptive about the 3-phase cascade and ends with "RETURN" rules.
If you see this with the current code, check `_TASK_PRELUDE` is being
prepended on `/ask` in `main.py`.

### "cuga.config loaded with settings.openai.toml"

**Symptom**: at startup the log says `loaded llm settings
*settings.openai.toml*` even though `LLM_PROVIDER=rits` is set.

**Cause**: `AGENT_SETTING_CONFIG` was set after cuga import. Move the
export earlier in your shell, or check `main.py` is doing the setdefault
at module top.

### "Failed to add policy: 'sqlite3.Connection' object has no attribute 'enable_load_extension'"

**Cause**: the venv's Python lacks loadable-sqlite-extensions. Rebuild
the venv with brew's python@3.12 (see Install above).

### "RITSChatModel: 403 Authentication failed"

**Cause**: the RITS key is invalid, expired, or scoped to a model you
didn't pick. Double-check the key is current and that
`LLM_MODEL=gpt-oss-120b` (not the default `llama-3-3-70b-instruct`,
which often has different access lists).

### "max_tokens must be at least 1, got -4536"

**Cause**: the supervisor's accumulated context exceeded the model's
window — older versions of this app had this. Current build trims
scout's per-category cap to 8 (was 15) and pre-initializes lists,
keeping the running context under control. If you re-introduce the
problem, look for: prelude growing beyond ~5KB, scout returning >12KB,
or specialist responses being unbounded.

### "Final answer has NO fenced ```json``` block"

**Cause**: the supervisor's planner stripped the writer's JSON fence
when re-emitting. The server's `_extract_leads_json` now handles four
shapes: fenced, bare, balanced-brace first, balanced-brace last. If
you see this, the writer probably returned no JSON at all — check the
diag's Message N for the writer's actual response.

### Cascade hangs / takes forever

**Cause**: the `LocalExecutor` defaults to a 30s timeout per code block.
Specialist CugaLite delegations regularly take 30–60s, so we
monkey-patch the floor to 180s in `main.py:_patch_executor_timeout`.
If a specialist consistently takes >180s, raise that ceiling — but
also investigate why (slow LLM? scout returning oversized JSON?).

---

## What's working as of this README

- ✅ Multi-agent supervisor with 7 specialists registered
- ✅ Skills loaded declaratively from `SKILL.md` + `tools.py`
- ✅ Three policies attach exactly once (intent_guard, tool_guide, output_formatter)
- ✅ Cascade: scout → parse → 5 specialist sweeps (partial) → writer
- ✅ Writer emits a fenced JSON board the UI parses + renders
- ✅ Defensive parser handles fenced, bare, and partial JSON

## What still has rough edges

- ⚠️ Writer often returns `deep_dive: false` even when sweeps fired —
  list-position alignment between sweeps is fragile. Fix: build per-
  candidate enrichment bundles in phase 2 instead of parallel lists.
- ⚠️ Supervisor's planner sometimes skips 4 of the 5 sweeps before
  jumping to the writer. Workaround for now: re-run the request.
- ⚠️ End-to-end latency is 1–3 min — gpt-oss-120b doing ~15 round-trips
  isn't fast.
