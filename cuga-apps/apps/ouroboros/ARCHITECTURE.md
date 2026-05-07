# Ouroboros — architecture

A FastAPI app that turns a place name and an optional category — *"find
restaurants in Pleasantville NY"*, *"salons in Brooklyn that need
booking"* — into a **ranked board of independent local businesses that
would benefit from a CUGA-powered conversational agent**, with tailored
cold-email drafts for the top 3.

It runs as a single Python process on a laptop, hosts its own UI, and
will (optionally) email you each finished board and re-run itself on a
schedule. CUGA is the spine: a `CugaSupervisor` orchestrating seven
specialist `CugaAgent`s, plus the recently-added **CUGA Loops** subsystem
for agent self-scheduling.

**Port:** 28822 → http://localhost:28822
**Loops dashboard:** http://localhost:28822/cuga/loops/

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                  ouroboros (this app, port 28822)                      │
   │                                                                        │
   │   ┌──────────────────────────────────────────────────────────────┐     │
   │   │  CugaSupervisor (model = RITS gpt-oss-120b, 100-step cap)    │     │
   │   │     │                                                         │     │
   │   │     ├─── delegate_to_scout ───────────┐                      │     │
   │   │     ├─── delegate_to_voice_of_customer ┐                     │     │
   │   │     ├─── delegate_to_site_auditor ────┐│                     │     │
   │   │     ├─── delegate_to_revenue_estimator┐││                    │     │
   │   │     ├─── delegate_to_person_finder ───┐│││  7 specialist     │     │
   │   │     ├─── delegate_to_stack_scanner ──┐│││││ CugaAgents       │     │
   │   │     └─── delegate_to_pitch_email_writer (synthesis)           │     │
   │   │                                                                 │     │
   │   │  Auto-injected (when enable_loops=True):                       │     │
   │   │     schedule_recurring · schedule_wakeup · cancel_loop ·       │     │
   │   │     list_my_loops    ← all in supervisor's execution sandbox  │     │
   │   │                                                                 │     │
   │   │  Policies (shared sqlite-vec store):                           │     │
   │   │     intent_guard · tool_guide · output_formatter               │     │
   │   └──────────────────────────────────────────────────────────────┘     │
   │            │                                                            │
   │            ▼                                                            │
   │   _handle_full_turn(question, thread_id, source, loop_id)               │
   │            │                                                            │
   │   ┌────────┴─────────────┬──────────────────┬─────────────────────┐    │
   │   ▼                      ▼                  ▼                     ▼    │
   │ runs/<thread>/*.json  session[t].leads  loops registry      email send │
   │ (per-turn metadata)   (right panel)     (cuga_loops table)  (smtplib) │
   └────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                ┌──────────────────────────────────┐
                │  Browser  (left chat + right     │
                │  lead board + email panel +      │
                │  loops dashboard link)           │
                └──────────────────────────────────┘
```

For installation + run + troubleshooting, see [README.md](README.md).
This file is the **architectural reference + complete story**.

## Diagrams

Two SVGs render the same picture from two angles:

- **[workflow.svg](workflow.svg)** — top-to-bottom data flow. Shows
  how a user request *or* a loop fire enters the same `_handle_full_turn`,
  runs through the 3-phase cascade (scout → 5 specialist sweeps →
  writer), and produces four outputs: lead board in the UI, run JSON
  on disk, optional email, and optional self-scheduled loop.
- **[stack.svg](stack.svg)** — layered view, browser at the top,
  external services at the bottom, with a sidecar storage column. Shows
  what lives in each layer and how the storage boundary divides what
  survives a process restart.

The legacy [architecture.png](architecture.png) (rendered from
[architecture.mmd](architecture.mmd) Mermaid) is still around for
historical reference.

---

## What problem does this solve?

The naive cold-outreach playbook for a SaaS company looks like:

1. Buy a list of local businesses.
2. Send the same email to all of them.
3. Hope something sticks.

It almost never does. The list is stale, the email is generic, the
businesses have no way to tell *why this product* would help *them
specifically*. Reply rates are well under 1%.

The opposite extreme — a human researcher producing one fully tailored
email per lead — works, but takes an hour per business. At even modest
volume, the unit economics break.

**Ouroboros sits in between.** Given a location, it produces a small,
ranked board of leads where each top-3 lead has:

- A **fit score** (1–10), grounded in concrete signals.
- A **pitch** that quotes a real customer review, names a missing site
  feature, or fingerprints an incumbent tool — never abstract.
- A **decision-maker name + best-guess email**, not `info@`.
- A **revenue-band estimate** so leads are sorted by recoverable revenue,
  not vibe.
- A **cold email draft** ready to send.

A human reading the board can decide who to actually email in minutes,
not hours. The output is auditable — every lead carries the evidence
that drove its score — and the per-run JSON is persisted so the same
question doesn't get re-researched a second time.

---

## Why CUGA? Why a multi-agent system?

The honest version of "why CUGA" for this app, by way of asking what
*wouldn't* work.

### What a one-shot LLM call gets you

`llm("Find me good restaurants in Pleasantville NY to sell my SaaS to.")`
will produce:

- A list of restaurants the LLM knows about — possibly closed, possibly
  fictional. No verification.
- Generic pitches like *"Restaurants need to engage customers online."*
  No evidence. No specificity.
- No decision-maker names; the model knows it can't dox real people, so
  it bails into vague advice.
- No way to re-rank, re-prompt one specialist, or update one signal —
  it's all one undifferentiated text blob.

Worse: there's nowhere for the model to *do work*. No sub-agent can call
the OpenStreetMap Overpass API to enumerate real businesses; no
sub-agent can fetch a business's website and parse it for missing
features; no sub-agent can search Tavily for a bad Yelp review and
quote it verbatim. A single LLM call has no tools.

### What "one CugaAgent with all 8 tools" would get you

Better — the agent can call OSM, fetch sites, search reviews. But:

- **Context bleed.** The OSM scout's output is 20–60 KB of business
  metadata. The site auditor's HTML excerpts are another 2–10 KB per
  business. The voice-of-customer's review hits add another 5 KB per
  business. By the time the writer needs to compose, the context window
  has 5–10× more raw data than the writer needs — and the planner has
  to keep track of *all of it* simultaneously.
- **Tool-selection drift.** With 8+ tools in one agent's surface, the
  planner re-discovers the same tool pattern many times. It might call
  `geocode` twice, mix up the stack-scanner output for one candidate
  with the site-auditor output for another, etc.
- **No isolation when one tool flakes.** A 502 from Tavily breaks every
  in-flight reasoning step in that one agent, not just the one
  specialist whose tool it was.

### What CUGA's multi-agent pattern gives us

A **`CugaSupervisor`** that knows *only* `delegate_to_<specialist>` —
nothing about `geocode` or `analyze_business_website` directly. Each
specialist is a **self-contained `CugaAgent`** with:

- Its own **`SKILL.md`** describing when to fire and what to return.
- Its own **`tools.py`** binding 1–3 native LangChain tools.
- Its own **planner context**: when the scout enumerates 60 businesses,
  the writer never sees the noise — it sees the writer's curated
  context blob.
- Its own **failure surface**: a 502 from Tavily fails one specialist's
  delegation, returns an empty string, and the planner moves on.

The supervisor's planner reasons in **delegations**, not tool calls.
Its planning surface is small (7 specialists) regardless of how many
underlying tools they wrap. New specialists can be added — `loop_scheduler`,
`competitor_finder`, `linkedin_enricher` — as separate skills folders,
no changes to the planner.

That's the architecture. The rest of this doc is the implementation.

---

## End-to-end flow (ASCII)

```
                                 ┌──────────────────────────────────────────────────────┐
                                 │              BROWSER  (left chat + right board)      │
                                 │   ✉️ Email button · 🔁 Loops link in header           │
                                 │   POST /ask {question, thread_id}                     │
                                 │   GET  /session/<thread_id>  (poll every 8s)          │
                                 │   POST /cuga/loops/api/create (inline schedule btn)   │
                                 └─────────────────────┬────────────────────────────────┘
                                                       │
                                                       ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            FastAPI server  (apps/ouroboros/main.py)                            │
│                                                                                                │
│   • _sessions[thread_id] = {target_location, categories, pitch_focus, leads, history}          │
│   • _handle_full_turn(question, thread_id, *, source, loop_id) — shared between /ask and       │
│     loop fires; stamps source = 'user' | 'loop' on every saved run                             │
│   • _TASK_PRELUDE: ~1.4K-token 3-phase contract prepended to every supervisor invocation       │
│   • _extract_leads_json + _normalize_leads_obj: tolerant parser for the writer's drift         │
│   • monkey-patches LocalExecutor timeout floor → 180s                                          │
│   • Email: _maybe_send_email_for_run fires after each run completes, async                     │
│   • Loops: _loop_invoke registered as the loops-service callback for "ouroboros_supervisor"    │
└─────────────────────────────────────────────────────┬──────────────────────────────────────────┘
                                                      │ supervisor.invoke(prelude + question, thread_id)
                                                      ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│                        CugaSupervisor   (LangGraph: prepare → call_model → execute → loop)     │
│                                                                                                │
│   • model:                  RITSChatModel("gpt-oss-120b", max_tokens=16000)                    │
│   • cuga_lite_max_steps:    100                                                                 │
│   • enable_loops:           True (auto-injects 4 loop tools into execution sandbox)            │
│   • Auto-injected tools:    delegate_to_<each-of-7-specialists>(task) → str                    │
│                             schedule_recurring · schedule_wakeup · cancel_loop · list_my_loops │
│   • Policies (shared sqlite-vec store at <sdk>/dbs/cuga.db):                                   │
│       intent_guard `ouroboros_abuse_guard`     — keyword-trigger refusal                       │
│       tool_guide   `prefer_independents`       — target_tools=[find_local_businesses]          │
│       output_formatter `leads_board_formatter` — keyword-trigger on writer's response          │
└─────────────────────────────────────────────────────┬──────────────────────────────────────────┘
                                                      │ delegate_to_<specialist>(task) — A2A
            ┌─────────────────────┬───────────────────┼───────────────────┬─────────────────────┐
            ▼                     ▼                   ▼                   ▼                     ▼
┌──────────────────────┐  ┌───────────────────┐  ┌──────────────────┐  ┌────────────────┐  ┌──────────────────────┐
│ scout                │  │ site_auditor      │  │ voice_of_customer│  │ person_finder  │  │ stack_scanner        │
│ ──────────────────── │  │ ───────────────── │  │ ──────────────── │  │ ────────────── │  │ ──────────────────── │
│ geocode              │  │ analyze_business_ │  │ search_reviews   │  │ search_owner   │  │ scan_business_stack  │
│ find_local_          │  │ website           │  │   ↑ web_search   │  │ guess_email_   │  │   regex over 33      │
│ businesses           │  │   httpx + html    │  │     via MCP      │  │ from_name      │  │   third-party        │
│   ↑ Overpass / OSM   │  │   strip + 9 cap + │  │                  │  │   ↑ web_search │  │   fingerprints       │
│                      │  │   8 freshness     │  │                  │  │     via MCP    │  │                      │
└──────────┬───────────┘  └─────────┬─────────┘  └────────┬─────────┘  └───────┬────────┘  └──────────┬───────────┘
           │                        │                     │                    │                       │
           ▼                        ▼                     ▼                    ▼                       ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
   │  Each specialist = a CugaAgent(model=…, tools=TOOLS_FROM_SKILL, special_instructions=SKILL.md)    │
   │  Each runs its own bounded CugaLite plan/execute graph in an isolated planner context.            │
   │  Returns a string (their "answer") to the supervisor's runtime variable.                          │
   └───────────────────────────────────────────────────────────────────────────────────────────────────┘

      ┌────────────────────┐  ┌──────────────────────────────────────────────────────────────────────┐
      │ revenue_estimator  │  │ pitch_email_writer                                                   │
      │ ────────────────── │  │ ──────────────────────────────────────────────────────────────────── │
      │ search_size_       │  │ TOOLS = []  (pure synthesis — no external lookups, no tools)         │
      │ signals            │  │ Receives the full enrichments[] bundle from the supervisor;          │
      │   ↑ web_search     │  │ produces the fenced JSON `leads` board + 2-paragraph summary.        │
      │ estimate_arr_band  │  │                                                                      │
      └────────────────────┘  └──────────────────────────────────────────────────────────────────────┘
```

---

## The 3-phase cascade (mandated by `_TASK_PRELUDE`)

The supervisor's planner doesn't decide *whether* to call specialists —
the prelude prescribes the cascade. It gets to decide *how* (which
candidates to skip, when to retry on errors, what to put in the
`writer_task` blob).

```
┌──────────────────── Phase 1 ─────────────────────────────┐
│ scout_result = await delegate_to_scout(task=user_question)│
│ data = json.loads(scout_result)                           │
│ candidates = data.get("candidates", []) or []             │
│ top = candidates[:3]                                      │
│ enrichments = {i: {"candidate": c} for i, c in            │
│                enumerate(top)}                             │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────── Phase 2 ─────────────────────────────────────┐
│ Each sweep WRITES into enrichments[i][<key>] for every candidate.      │
│ When a sweep skips a candidate (no website), it stores "" so the slot  │
│ still exists. By phase 3 every candidate has its full bundle.          │
│                                                                         │
│ Sweep 1 (voc):     enrichments[i]["voc"]    = await voice_of_customer  │
│ Sweep 2 (audit):   enrichments[i]["audit"]  = await site_auditor       │
│ Sweep 3 (revenue): enrichments[i]["revenue"]= await revenue_estimator  │
│ Sweep 4 (person):  enrichments[i]["person"] = await person_finder      │
│ Sweep 5 (stack):   enrichments[i]["stack"]  = await stack_scanner      │
└────────────────────┬───────────────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────── Phase 3 ─────────────────────────────────────────┐
│ enriched_list = [enrichments[i] for i in range(len(top))]              │
│ # one self-contained dict per top candidate, no positional alignment   │
│                                                                         │
│ writer_task = "Build the final ranked lead board…\n\n" + json contexts │
│ final = await delegate_to_pitch_email_writer(task=writer_task)         │
└────────────────────┬─────────────────────────────────────────────────┘
                     │
                     ▼
       writer's output = fenced JSON + 2-paragraph summary
                     │
                     ▼
       FastAPI parses JSON → session["leads"] → UI renders right panel
                     │
                     ▼
       Optional: schedule_recurring(...) if user said "watch every X"
                     │
                     ▼
       runs/<thread>/<ts>.json saved with source='user' or 'loop'
                     │
                     ▼
       _maybe_send_email_for_run() fires (if recipient configured)
```

The biggest historical failure mode (parallel-list alignment) was fixed
by moving to per-candidate enrichment **bundles** (the `enrichments`
dict). Each entry is self-contained, so the writer never has to zip
five parallel lists.

---

## Per-specialist fact sheet

| Agent | What the planner sees in `delegate_to_<X>` | Native tools | Pre-bound from MCP |
|---|---|---|---|
| `scout` | "Resolve a place name to coordinates and surface candidate local businesses by category from OpenStreetMap." | `geocode`, `find_local_businesses` | — |
| `site_auditor` | "Fetch a business website and classify it on capability gaps and freshness flaws." | `analyze_business_website` | — |
| `voice_of_customer` | "Mine review-site snippets and complaint posts for verbatim friction quotes about a specific business." | `search_reviews` | `web_search` |
| `person_finder` | "Find a likely decision-maker for a business and propose a best-guess direct email with a confidence rating." | `search_owner`, `guess_email_from_name` | `web_search` |
| `stack_scanner` | "Fingerprint third-party tools embedded on a business's website (OpenTable, Calendly, Toast, Square, Resy, Zocdoc, etc.)." | `scan_business_stack` | — |
| `revenue_estimator` | "Estimate the annual-revenue band of a business from public size signals." | `search_size_signals`, `estimate_arr_band` | `web_search` |
| `pitch_email_writer` | "Synthesize the final ranked lead board and a tailored cold email per deep-dived lead." | (none — pure synthesis) | — |

A specialist is **declarative**: edit the `SKILL.md` and the change
takes effect on the next process restart. No code changes needed unless
you're adding a new tool.

---

## Policies — quality guards on the supervisor

CUGA policies are runtime filters that fire when their trigger
matches. Ouroboros attaches three at startup
([main.py:_attach_policies](main.py)). All three live in the shared
sqlite-vec store at `<sdk>/dbs/cuga.db`, so we add each one **once** on
a representative agent and let the runtime trigger system scope
enforcement at call time.

| Policy | Type | Where it fires | Why |
|---|---|---|---|
| `ouroboros_abuse_guard` | `intent_guard` | Any specialist's input matching keywords `harass`, `dox`, `stalk`, `scrape personal`, `find someone's home address`, `track down` | Hard refusal. Ouroboros is for finding businesses, not people. The keyword list is intentionally loud-and-narrow — high precision, low recall is fine because the refusal is graceful. |
| `prefer_independents` | `tool_guide` | Only when `find_local_businesses` is invoked (`target_tools` scope) | Drops global chains (Starbucks, McDonald's, etc.) from the candidate shortlist. Independent 1–5-location businesses are the target — chains have central procurement and don't make local SaaS decisions. |
| `leads_board_formatter` | `output_formatter` | Writer's response only (`keywords=["leads", "lead board", "shortlist", "ranked"]`) | Forces the writer to emit fenced ```json``` + 2-paragraph summary. Without this, the writer's freeform prose breaks the right-panel renderer. |

`reset_policy_storage=True` on the *first* agent built clears the
shared DB so re-runs don't accumulate duplicate copies of the same
policy.

---

## CUGA Loops — agent self-scheduling

Recently added. Lets the supervisor (or anything that calls
`POST /cuga/loops/api/create`) schedule itself to re-run later.

### What it gives you

Type *"find restaurants in Pleasantville NY and watch every 5
minutes for new ones"*. The supervisor:

1. Runs the cascade as usual (phases 1–3 → writer's lead board).
2. In a separate code block, calls `schedule_recurring(cadence="5m", prompt="find restaurants in Pleasantville NY (diff against last run)")`.
3. Mentions the loop id in its reply.

The CUGA loops scheduler then fires the saved prompt every 5 minutes
on the same `thread_id`, going through the **same** `_handle_full_turn`
path as a manual ask — so each fire produces a real lead board, gets
saved as a `runs/<thread>/<ts>.json` with `source="loop"`, and (if
email is configured) sends a "🔁 LOOP FIRE" email.

### How the supervisor calls schedule_*

CUGA supervisors normally only see `delegate_to_<specialist>` in their
execution sandbox. The loops integration injects four tools as
**first-class supervisor callables** (not specialist tools — the
supervisor is the single decision-maker):

```python
loop_id = await schedule_recurring(
    cadence="5m",          # interval shorthand, raw cron, or NL ("daily", "weekly")
    prompt=user_question + " (diff against last run)",
)
```

`enable_loops=True` on the `CugaSupervisor` constructor flips this on.
Specialists' tool surfaces stay clean — no loops tools leak into them.

### LLM-free path: HTTP create endpoint

Apps and UIs that want to schedule without invoking the LLM use:

```bash
curl -X POST http://localhost:28822/cuga/loops/api/create \
  -H 'content-type: application/json' \
  -d '{"agent_name": "ouroboros_supervisor",
       "thread_id":  "abc-...",
       "prompt":     "find restaurants in pleasantville NY",
       "cadence":    "weekly"}'
```

Used by the inline 🔁 button under each user message.

### What gets saved when a loop fires

Each fire writes:
- A row in `cuga_loop_runs` (registry; truncated answer + outcome).
- A full `runs/<thread>/<ts>.json` with `source="loop"`, `loop_id="loop_abc123"`.
- The lead board to `_sessions[thread_id]["leads"]`, so if the user
  has the page open they see the right panel update.
- A "🔁 LOOP FIRE" email if recipient + SMTP creds are configured.

### Distinguishing user vs loop in the UI

- **Past runs drawer** — loop rows get a purple left edge + `🔁 loop · loop_abc…` badge linking to the loops dashboard. User rows get a gray `👤 user` badge.
- **Email subject** — `Ouroboros · 🔁 LOOP FIRE · …` vs `Ouroboros · 👤 USER REQUEST · …`.
- **Loops dashboard** at `/cuga/loops/` — full table with status, cadence, created-at, next-fire, last-fire timestamps; click any loop to see its last 25 runs with outcomes; pause / resume / run-now / delete.

---

## Email panel

Configured per-app in `.email_store.json` (UI-editable). Sends an HTML
email after every completed run — user-triggered or loop-triggered.

### Configuration

The ✉️ Email button in the header opens a modal with:
- **Recipient** — required; emails are off if empty (no master toggle).
- **Min leads** — skip noisy zero-lead runs.
- **Per-source toggles** — 👤 user / 🔁 loop independently on/off.
- **SMTP creds** — host/port/username/password/from. Defaults to `anupama.murthi@gmail.com` everywhere except password. UI overrides win, env vars (`SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL`) are the fallback.
- **Send test email** — uses the form's current values, no save needed.

The password is masked on read (`•••` sentinel). Sending the sentinel back means "keep the saved password unchanged."

### Email body

A dark-themed HTML email with:
- A colored source banner (purple "🔁 LOOP FIRE" or gray "👤 USER REQUEST").
- The user's question, location, lead count, elapsed time, thread tag, and (for loop fires) the loop id.
- A 3-row table with the top deep-dive leads (name + fit_score + pitch snippet).

### How it's wired

`_maybe_send_email_for_run()` is called via `asyncio.create_task(...)` after `_save_run` returns — fire-and-forget, never blocks the response. The gate is: `recipient is non-empty` AND `SMTP creds available` AND `per-source toggle is on for this run's source` AND `leads_count >= min_leads`.

---

## Per-turn run history

Every supervisor invocation persists `runs/<thread_id>/<YYYYMMDDTHHMMSSZ>.json`
with the full record:

```json
{
  "thread_id":      "...",
  "timestamp":      "2026-05-06T18:32:40Z",
  "started_at":     "...",
  "elapsed_ms":     132040,
  "elapsed_human":  "2m 12s",
  "question":       "find restaurants in pleasantville NY",
  "answer_full":    "Here's the lead board…\n\n```json{...}```",
  "leads":          { "location": "...", "leads": [...] },
  "leads_count":    3,
  "agent_trace":    { "counts": {"scout": 1, "voice_of_customer": 3, ...}, "total_calls": 11 },
  "supervisor_state": { "stages": [...], "variables": {...} },
  "source":         "user",     // ← who triggered this run
  "loop_id":        null         // ← set for source="loop"
}
```

**Endpoints**:
- `GET /runs` — every run on disk across every thread (newest first)
- `GET /runs/{thread_id}` — runs for one thread
- `GET /runs/{thread_id}/{filename}` — full record (used by the UI's "view trace" modal)

**Past runs drawer** (right side of chat panel):
- Toggle scope between "this thread" and "all threads".
- Each row shows the source badge, timestamp, elapsed, lead count, agent fan-out pills (`scout×1`, `voc×3`, …), and a "view trace" link for the full agent trace.
- Click any row to load that run's lead board into the right panel.

---

## Inline message scheduler

After every user message in the chat, a discreet row appears under the
text bubble:

```
🔁 Schedule this · [daily ▾] [Set]
```

The cadence dropdown offers `5m / 30m / 1h / 6h / daily / weekly`. Clicking **Set** posts to `POST /cuga/loops/api/create` with the message text as the prompt and `agent_name=ouroboros_supervisor`. The row replaces with `🔁 Scheduled daily · loop_abc… · Cancel`. Cancel does an inline `DELETE /cuga/loops/api/<id>`.

This is the lowest-friction path to "schedule this exact question" — it
doesn't invoke the LLM at all, just creates a loop directly. The
supervisor will be invoked when the loop fires, by the same
`_handle_full_turn` plumbing as a manual ask.

---

## MCP integration

Three specialists need `web_search` from the hosted `mcp-web` server.
Their `tools.py` exposes a `bind_web_search(fn)` hook;
`specialists.py` resolves the MCP-loaded tool once at startup via
`_mcp_bridge.load_tools(["web"])` and calls each
`bind_web_search(...)` with that coroutine. The skill never imports MCP
directly.

```
   apps/_mcp_bridge.py                 host bridge
        │
        ▼
   mcp-web (Code Engine)               Tavily-backed search tool
        ▲
        │ bind_web_search(coro)
        │
   skills/voice_of_customer/tools.py
   skills/person_finder/tools.py
   skills/revenue_estimator/tools.py
```

`CUGA_TARGET=ce` (default in `main.py`) points the bridge at the hosted
Code Engine MCPs.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | liveness |
| POST | `/ask` | run one supervisor turn (source='user') |
| GET  | `/session/{thread_id}` | current session state (right panel polls this) |
| GET  | `/runs` | every saved run on disk |
| GET  | `/runs/{thread_id}` | runs for one thread |
| GET  | `/runs/{thread_id}/{filename}` | one run's full JSON |
| GET  | `/email/config` | current email config (password masked) |
| POST | `/email/config` | save email config (password preserved if blank/sentinel) |
| POST | `/email/test` | send test email using request body's settings |
| GET  | `/cuga/loops/` | loops dashboard (HTML) |
| GET  | `/cuga/loops/api/list` | every loop in the registry |
| POST | `/cuga/loops/api/create` | create a loop (LLM-free path) |
| POST | `/cuga/loops/api/{id}/{pause\|resume\|run}` | loop actions |
| DELETE | `/cuga/loops/api/{id}` | delete loop + runs |
| GET  | `/specialists` | active specialist names (debug) |
| GET  | `/` | HTML UI |

---

## CUGA capabilities tapped

| Capability | Where wired | What it gives us |
|---|---|---|
| **`CugaSupervisor`** | `main.py:make_supervisor` | A2A orchestration of 7 specialist agents |
| **`CugaAgent`** (×7) | `specialists.py:_make_agent` | Per-specialist plan/execute graph in isolated context |
| **`CugaLite` step caps** | `cuga_lite_max_steps=100` on supervisor | Bounded planner per agent, no runaway loops |
| **Skills (declarative)** | `skills/<name>/SKILL.md` | Specialist's body becomes `special_instructions` at startup |
| **Skills `tools.py`** | `skills/<name>/tools.py` → `TOOLS = [...]` | Native LangChain `@tool` wiring |
| **Policies — `intent_guard`** | `_attach_policies` → `add_intent_guard` | Refuse harassment / doxxing intents, keyword-triggered |
| **Policies — `tool_guide`** | `_attach_policies` → `add_tool_guide(target_tools=[...])` | Skip-chains nudge scoped to one tool only |
| **Policies — `output_formatter`** | `_attach_policies` → `add_output_formatter(keywords=[...])` | Enforce fenced JSON + 2-paragraph summary |
| **`policies.clear()`** | once at supervisor init | Process restarts don't accumulate stale policies |
| **MCP bridge integration** | `specialists.py:_resolve_web_search` + per-skill `bind_web_search` | 3 specialists pull from Tavily without leaking MCP into the skill |
| **Per-specialist `cuga_folder`** | `_DIR / .cuga_<skill_name>` | Per-specialist filesystem-sync of policies; skill artifacts isolated |
| **CUGA Loops** | `enable_loops=True` on `CugaSupervisor` + custom `_loop_invoke` callback | Supervisor self-scheduling + custom run-save/email logic per fire |

---

## SDK quirks worth knowing (collected the hard way)

These are non-obvious behaviors of the `feat/skills-support` CUGA branch
discovered while building Ouroboros. Future apps on this branch should
factor them in.

1. **`CugaSupervisor.description=` is dead.** Stored on `self._description`
   but never rendered into the supervisor's prompt template — the template
   hardcodes `special_instructions=None`. The only place to inject
   orchestration rules is the user-message itself (we prepend `_TASK_PRELUDE`).

2. **Internal CUGA nodes ignore the `model=` kwarg.** Each `CugaAgent`'s
   `model=` is used for the *outer* planner only. Sub-nodes (planner,
   shortlister, code-agent, answer, …) call `LLMManager().get_model(
   settings.agent.X.model)` directly, which reads from
   `AGENT_SETTING_CONFIG`'s TOML. So you must set `AGENT_SETTING_CONFIG`
   before *any* cuga import in the process — module-top, not inside
   `make_supervisor()`.

3. **The supervisor's code extractor is fragile to triple-backticks.**
   `extract_and_combine_codeblocks` uses `re.findall(r'```python(.*?)```',
   text, re.DOTALL)`. Non-greedy regex closes on the first `` ``` ``, so a
   regex literal like `r"```json...```"` *inside* the planner's code closes
   the fence early → block silently dropped → "no code, final answer"
   misclassification. Lesson: never put triple-backticks in the prelude or
   in any string the planner might quote.

4. **`LocalExecutor` hardcodes a 30s timeout** per code block. Specialist
   CugaLite delegations regularly take 30–60s, so we monkey-patch the
   timeout floor to 180s in `main.py`.

5. **Policy storage is a shared SQLite-vec DB at `<sdk>/dbs/cuga.db`** —
   adding the same policy from multiple agents in one process creates
   duplicates and persists across runs. We add each policy ONCE on a
   representative agent and call `policies.clear()` at startup.

6. **`platform == "rits"` in CUGA's `LLMManager` instantiates `ChatOpenAI`
   with the toml's `url`** (default `http://localhost:4000`). That expects
   a LiteLLM proxy at :4000 to rewrite OpenAI's `Bearer <key>` into RITS's
   `RITS_API_KEY: <key>`. Without the proxy, internal CUGA calls 401/403.

7. **Scout's CugaLite-generated answer can truncate.** Without a
   `max_tokens` cap, RITS prod defaults to a low limit (~1024 tokens). We
   set `RITSChatModel.max_tokens=16000` and pin it in the payload (`_llm.py`).

8. **`auto_load_policies` and `reset_policy_storage` interact** — the
   storage clear happens BEFORE filesystem auto-load, so policies on disk
   come back unless you `auto_load_policies=False` on every agent. We do.

9. **Supervisor planner can only call `delegate_to_<X>` by default.**
   Adding tools via specialists doesn't make those tools callable from the
   supervisor's code — they're scoped to specialists. CUGA Loops solves
   this for the schedule_* tools by injecting them directly into the
   supervisor's execution sandbox (`enable_loops=True` toggles this).

10. **Loops registration races.** `CugaSupervisor._ensure_loops_initialized`
    calls `svc.register_agent(name, default_callback)` on first invoke. If
    your app pre-registers a custom callback (as ouroboros does for
    `_loop_invoke`), the SDK's auto-register would overwrite it — except
    we patched the SDK to skip if the name is already registered. Your
    app's `register_agent(...)` must run BEFORE the first
    `supervisor.invoke()` for this to work.

11. **Pydantic v2 + FastAPI + `Optional[Model] = None` body params are
    flaky.** Sometimes the body deserializes as `None` even when valid
    JSON is sent. Use a required `req: _EmailCfgReq` signature instead.

12. **Pydantic v2 rejects `""` as `int`.** Browser inputs send empty
    strings for cleared number fields. Add a `@field_validator(...,
    mode="before")` that coerces `""` and `None` to a default int.

13. **Writer drift.** The pitch_email_writer specialist sometimes returns
    `lead_board` instead of `leads`, `company_name` instead of `name`,
    etc. `_normalize_leads_obj` translates writer drift into the canonical
    `{location, leads:[{name, …}]}` shape before storing.

---

## Repo layout

```
apps/ouroboros/
├── main.py                  FastAPI server, CugaSupervisor build, policy attach,
│                            _TASK_PRELUDE, json extractor + normalizer, executor
│                            monkey-patch, email send, loops registration
├── specialists.py           7 factories: each loads one skill into a CugaAgent
├── ui.py                    dark two-panel UI (chat + lead board + email modal +
│                            loops link + inline-schedule control + past runs)
├── diag.py                  one-shot end-to-end diagnostic (dumps full trace)
├── README.md                install, run, troubleshoot — start here
├── ARCHITECTURE.md          this file — design + agents + cascade + loops + email
├── requirements.txt         dependency hints (cuga is a path install)
├── .email_store.json        UI-editable email config (created on first save)
└── skills/                  the seven specialists' artifacts
    ├── scout/               geocode + Overpass
    │   ├── SKILL.md
    │   └── tools.py
    ├── site_auditor/        capability + freshness signal classifier
    ├── voice_of_customer/   web_search → friction quotes
    ├── person_finder/       owner search + email pattern guesses
    ├── stack_scanner/       OpenTable / Calendly / Toast / etc fingerprint
    ├── revenue_estimator/   size signals → coarse ARR band
    └── pitch_email_writer/  no tools — synthesis from collected signals
```

After first run, you'll also see seven `.cuga_<specialist>/`
directories. Those are CUGA's per-agent filesystem-sync of attached
policies. Safe to delete; regenerated on next start.

The CUGA loops registry is in the SDK's shared sqlite DB
(`<sdk>/dbs/cuga.db`, tables `cuga_loops` + `cuga_loop_runs`), not
inside the app.

---

## When you might *not* want this pattern

The multi-agent + cascade pattern is designed for **researchy, multi-step
tasks where each step has its own tool surface and the synthesis benefits
from isolated planner contexts**. Cases where it's overkill:

- **The task fits in one LLM call.** Don't wire a supervisor + 7
  specialists for "summarize this paragraph." Use a `CugaAgent` directly.
- **Sequential, not branching.** If your steps are A → B → C with no
  parallelism, that's a pipeline. CUGA's planner is overhead vs. just
  calling each step in Python.
- **The output isn't structured.** Multi-agent shines when the writer
  needs a clean handoff from each researcher's structured output. If the
  final answer is freeform prose with no schema, the orchestration cost
  doesn't pay back.
- **You don't need the loops/email/runs scaffolding.** Those are app-
  level scaffolding that exist because Ouroboros is a long-running tool;
  for a one-shot script they're dead weight.

For everything else — research-style tasks where the value is in
*decomposed* signals each grounded in real evidence — the pattern pays
for itself by the second specialist.

---

## Outstanding rough edges

The cascade now completes end-to-end and produces an 8-lead board. The
biggest historical failure mode (parallel-list alignment) was fixed by
moving to per-candidate enrichment bundles. Two known soft spots
remain:

- **The supervisor's planner sometimes runs only one specialist sweep
  before jumping to the writer.** The "do all 5 sweeps" rule is in the
  prelude but doesn't always stick on gpt-oss-120b. Mitigation already
  in place: bundle pattern means even a partial sweep produces a usable
  bundle. If reliability degrades further, the next step is to drive
  the supervisor in three separate `/ask` invocations from main.py
  (one per phase) so the planner sees a smaller decision space per
  call — keeps multi-agent intact, just moves the `for phase in [1,2,3]`
  loop out of the LLM and into Python.
- **Writer drift on the JSON schema.** The writer occasionally swaps
  `leads` ↔ `lead_board` and `name` ↔ `company_name`. The
  `_normalize_leads_obj` post-processor catches the common variants;
  the structural fix is JSON-schema validation on the writer's output
  with a re-prompt loop. Worth doing if the variants get exotic.
