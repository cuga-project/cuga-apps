# Smart Todo — Architecture Dilemma

A conversation working through the design decisions before building `smart_todo_new`.

---

## The Core Question

> Can just tools solve the smart todo problem? Can I just use CugaAgent and not use any cuga++ features?

**Short answer:** Tools solve the *data* problem. The *time* problem always requires a background process.

- `save_todo`, `list_todos`, `mark_done` — pure agent tools, no cuga++ needed
- "remind me at 8pm" — agent saves the row, but *something* has to fire at 8pm
- That something is either cuga++'s CugaRuntime/CugaWatcher, or you reinvent it

---

## The Four Layers

### cuga (pure reasoning)
- `CugaAgent` — takes a message + tools, calls LLM, returns an answer
- Stateful via `thread_id`
- Knows nothing about scheduling, channels, delivery

### cuga++ (infrastructure)
- **Channels**: `RssChannel`, `CronChannel`, `EmailChannel`, `SlackChannel`, `PollDataChannel` (new)
- **CugaRuntime**: wires DataChannels → buffer → TriggerChannel → CugaAgent → OutputChannels
- **CugaHost**: daemon managing multiple runtimes via REST API (`/runtime` endpoints)
- **CugaHostClient**: HTTP client wrapping those endpoints
- **ConversationGateway**: always-on chat, wraps CugaAgent

### app (what you write)
- `agent.py` — `make_agent()` with app-specific tools
- `store.py` — app data (SQLite)
- `skills/*.md` — system prompt
- `host_factories.py` — factory functions: config dict → CugaRuntime
- `cuga_pipelines.yaml` — which runtimes to auto-start on boot
- `chat.py` — thin CLI (~25 lines)

### tools (what the agent can call)
- **Capability tools** (cuga-channels provides): `make_web_search_tool()`, `make_email_tool()` (new), `make_slack_tool()` (new)
- **App-specific tools**: `save_todo`, `list_todos`, `mark_done`, `list_due`
- **Config tools** (thin wrappers around CugaHost REST API): `configure_digest`, `stop_digest`, `get_digest_status`

Config tools are how the **conversational layer controls the background layer**. The agent calls `configure_digest("0 9 * * *")` and the tool does the `PUT /runtime/digest` call.

---

## NL Utterance Routing

Every utterance falls into one of three buckets:

```
"what's on my todo list?"
"add a todo to review notes"
"remind me in 2 min to email XYZ"
        ↓
   DIRECT → CugaAgent handles immediately via tools
   (answer comes back in same turn)


"watch arxiv hourly, send digest at midnight"
"monitor HuggingFace for LLM news"
        ↓
   PIPELINE SETUP → PipelineBuilder extracts config
                  → CugaHostClient.start_runtime()
                  → new CugaRuntime starts in background


"send my digest at 9am instead of 8am"
"stop the arxiv pipeline"
        ↓
   RUNTIME CONTROL → config tool → CugaHost REST API
                   → existing runtime updated/stopped
```

---

## Why newsletter_new Needed PipelineBuilder

Each utterance produces a **different runtime shape**:

```
"watch arxiv hourly, digest at midnight"
→ RssChannel(url=arxiv) + CronChannel("0 0 * * *") + EmailChannel(to=...)

"monitor HuggingFace and VentureBeat, 8pm daily"
→ RssChannel(hf) + RssChannel(vb) + CronChannel("0 20 * * *") + EmailChannel(to=...)
```

PipelineBuilder extracts that variable channel config from NL so `CugaHostClient.start_runtime()` gets the right parameters.

---

## Why smart_todo Does NOT Need PipelineBuilder

The runtimes are **pre-defined and fixed**:

```
smart-todo-gateway         ← always running, same shape
smart-todo-reminder-poller ← always running, same shape
smart-todo-digest          ← always running, schedule configurable but not variable
```

NL utterances write **data** to the store. Pre-defined pipelines read that data.

| App | NL utterance does | Pipeline shape |
|---|---|---|
| newsletter_new | defines a new pipeline | variable, one per utterance |
| smart_todo | writes a data row | fixed, defined at startup |

---

## Three Runtimes Inside CugaHost

```
CugaHost (always alive)
│
├── smart-todo-gateway          [ConversationGateway]
│     └── CugaAgent
│           ├── save_todo
│           ├── list_todos
│           ├── mark_done
│           ├── configure_digest   ← reconfigures digest runtime via CugaHostClient
│           └── stop_digest
│
├── smart-todo-reminder-poller  [CugaRuntime, per_item=True]
│     ├── PollDataChannel(list_due, every=1min)   ← NEW in cuga-channels
│     ├── CronChannel("* * * * *")
│     └── CugaRuntime routes per item → EmailChannel or SlackChannel
│
└── smart-todo-digest           [CugaRuntime]
      ├── CronChannel(user-configured schedule)
      ├── CugaAgent (list_todos active + done, compose HTML)
      └── EmailChannel(to=user)
```

---

## The Delivery Channel Problem

### For digest: cuga++ OutputChannels work perfectly

```python
CugaRuntime(output_channels=[EmailChannel(to="me@x.com")])
```

Agent produces one answer → EmailChannel delivers it. cuga++ owns delivery entirely.

### For per-item reminders: the OutputChannel model breaks

OutputChannel model: **one delivery config, wired at runtime creation, fires once per trigger.**

But reminders are per-item with different destinations:
```
Reminder 1 → alice@x.com (email)
Reminder 2 → #bob-reminders (slack)
Reminder 3 → charlie@x.com (email)
```

### The Solution: per_item mode in CugaRuntime (Option 2)

Add to CugaRuntime:

```python
CugaRuntime(
    output_channels={
        "email": EmailChannel(...),
        "slack": SlackChannel(...),
    },
    delivery_key="delivery_channel",  # field name in each buffered item
    per_item=True,
)
```

**Current behavior** (`per_item=False`, default):
```
buffer [item1, item2, item3]
  → one agent call with all items → one answer → deliver to ALL output channels
```

**New behavior** (`per_item=True`):
```
buffer [item1, item2, item3]
  → for each item:
      agent.invoke(this item only) → answer
      → item["delivery_channel"] → pick output channel
      → deliver to THAT channel only, with item["delivery_target"] as recipient override
```

### What changes

| What | Where |
|---|---|
| `per_item` mode + dict `output_channels` | `CugaRuntime._on_trigger()` |
| `delivery_target` override in metadata | `EmailChannel`, `SlackChannel` |
| `delivery_channel` + `delivery_target` columns | `store.py` |
| newsletter_new | **zero changes** — list-based `output_channels` unchanged |

---

## Full Flow Example

```
User: "remind me at 8pm to ping the team in slack #general"
  ↓
Gateway agent:
  save_todo(
    content="ping the team",
    due_date="today 20:00",
    delivery_channel="slack",
    delivery_target="#general"
  )
  → "⏰ Reminder set for 8pm — will send to #general"

8:00pm — PollDataChannel finds the row, adds to buffer
8:00 or :01 — CronChannel fires

CugaRuntime (per_item=True):
  item = {content: "ping the team", delivery_channel: "slack", delivery_target: "#general"}
  → agent.invoke("Compose a brief reminder for: ping the team")
  → answer: "Hey team — reminder to check in!"
  → item["delivery_channel"] = "slack"
  → SlackChannel.deliver(answer, metadata={"delivery_target": "#general"})
  ✓
```

---

## New cuga-channels Additions Required

| Addition | Why |
|---|---|
| `PollDataChannel(source_fn, every_minutes)` | Generic callable-based DataChannel. Avoids LLM cost when buffer is empty (CugaRuntime skips agent if no due items). |
| `per_item=True` + dict `output_channels` in `CugaRuntime` | Per-item routed delivery without agent tools handling channels. |
| `delivery_target` override in `EmailChannel`, `SlackChannel` | Item-level recipient overrides runtime-level default. |

---

## What Does NOT Change

- `newsletter_new` — zero changes, uses existing list-based OutputChannels, `per_item` defaults to False
- `CugaAgent` — no changes, just gets different tools per runtime
- `CugaHost` REST API — no changes
- `PipelineBuilder`, `CugaREPL` — not used by smart_todo at all
