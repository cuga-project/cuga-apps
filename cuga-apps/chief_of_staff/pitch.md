# Chief of Staff & Toolsmith
## A self-extending agent platform

---

## The problem

Every enterprise AI assistant hits the same wall:

> *"I'd like to do X."*
> *"I don't have a tool for that."*

Today, the answer is **a human writes a new tool, ships it, redeploys**. That cycle takes hours-to-weeks. It doesn't scale across hundreds of internal apps, thousands of public APIs, and an even larger long tail of websites that expose data only through a browser.

**The bottleneck is humans wiring tools.** The agent's capability ceiling is set by its tool inventory at deploy time — not by what the user actually needs.

---

## The vision

> An agent whose **tool universe grows with use**.
>
> When the planner can't fulfill a request with the tools it has, a second agent — **Toolsmith** — autonomously **builds and registers** the missing tool while the user waits.

```
   User asks something                      Tool universe grows
        │                                          ▲
        ▼                                          │
   ┌──────────┐    "I lack a tool"      ┌──────────────────┐
   │  cuga    │ ────────────────────►   │     Toolsmith    │
   │ planner  │                         │  (ReAct agent)   │
   └────┬─────┘  ◄──── new tool ────    └────────┬─────────┘
        │                                        │
        │ uses                                   │ acquires from
        ▼                                        ▼
   ┌──────────────────────────────────────────────────────┐
   │          Catalog · OpenAPI · Browser tasks           │
   └──────────────────────────────────────────────────────┘
```

The catch: this only works if you have a *durable* agent that persists what it builds, validates it before exposing it, manages the credentials authenticated APIs need, and can fall back to browser automation when no API exists. That's what we built.

---

## Where cuga fits

cuga is **the planner / executor**: given a user message and a tool set, it decides what to call, in what order, and synthesizes the answer. It already does this very well.

What cuga does *not* do:
- It doesn't grow its toolset by itself.
- It doesn't manage per-user secrets for authenticated APIs.
- It doesn't fall back to browser automation when an API doesn't exist.
- It doesn't persist anything — toolset is fixed at startup.

Toolsmith is the surrounding system that makes those things true. **cuga remains untouched and swappable** — a different planner could take its place behind the same HTTP contract, and the rest of the stack would not change.

---

## Architecture at a glance

```
                              ┌───────────────────────────────────┐
                              │       Chief of Staff UI           │
                              │   (chat + tool inventory + vault) │
                              └─────────────────┬─────────────────┘
                                                │  /chat, /tools, /vault
                                                ▼
                              ┌───────────────────────────────────┐
                              │         Backend orchestrator      │
                              │  (the seam — thin coordinator)    │
                              └────────┬───────────────┬──────────┘
                                       │               │
                           "plan & execute"    "acquire missing tool"
                                       │               │
                                       ▼               ▼
                           ┌──────────────────┐  ┌──────────────────┐
                           │   cuga adapter   │  │    Toolsmith     │
                           │  (planner shell) │  │  (durable agent) │
                           │                  │  │                  │
                           │  • cuga.sdk      │  │  • LangGraph     │
                           │  • MCP tools     │  │    ReAct loop    │
                           │  • per-call      │  │  • Coder         │
                           │    tool tracker  │  │    (gpt-oss /    │
                           │  • disable mask  │  │     Claude)      │
                           │                  │  │  • Vault         │
                           └────────┬─────────┘  └────────┬─────────┘
                                    │                     │
                                    │ MCP servers         │ acquires from
                                    ▼                     ▼
                           ┌──────────────────┐  ┌──────────────────────┐
                           │  web · finance   │  │  Catalog (curated)   │
                           │  geo · code      │  │  OpenAPI (apis.guru) │
                           │  local · text …  │  │  Browser tasks       │
                           └──────────────────┘  │  (Playwright runner) │
                                                 └──────────────────────┘
```

Five services. Each is independently deployable, independently swappable, talks over HTTP. The orchestrator does no AI work — it routes.

---

## Why "Chief of Staff"?

The orchestrator is the **thin coordinator** between the user and a team of specialists (cuga the planner, Toolsmith the builder, the MCP servers as departments). The metaphor:

- A real Chief of Staff doesn't decide strategy — **they route requests**.
- They don't do the specialist work — **they coordinate the specialists who do**.
- They maintain the inventory of who-does-what.
- They shield the principal from operational chaos.

That's exactly the job of this layer: **one face to the user, many specialists behind it**. The CoS is not the smart one — that's the planner. CoS is the indispensable connective tissue.

The name is just a label and is swappable (Concierge / Conductor / Switchboard would all fit). What matters is the role: **a thin human-facing surface that owns the orchestration, owns the inventory, and stays out of the way**.

---

## How acquisition works

When cuga detects it lacks a fitting tool, it returns a structured **gap**: `{capability, inputs, expected_output}`. The orchestrator hands the gap to Toolsmith, which runs a tiered acquisition strategy:

```
                     ┌──────────────────────────────┐
   gap from cuga ──► │  Tier 1: Curated catalog     │  fast, deterministic
                     │  (ours, hand-picked APIs)    │  e.g. jokes, REST Countries
                     └──────────┬───────────────────┘
                                │ no match
                                ▼
                     ┌──────────────────────────────┐
                     │  Tier 2: OpenAPI directory   │  general — apis.guru
                     │  + Coder generates client    │  any public REST API
                     │    code (gpt-oss / Claude)   │
                     └──────────┬───────────────────┘
                                │ no match
                                ▼
                     ┌──────────────────────────────┐
                     │  Tier 3: Browser task        │  last resort — Playwright
                     │  (DSL: navigate, click,      │  for sites with no API
                     │   extract, …)                │
                     └──────────┬───────────────────┘
                                │
                                ▼
                     ┌──────────────────────────────┐
                     │      Probe before registry   │  validate it actually works
                     │    Persist artifact to disk  │  before exposing to cuga
                     │    Hot-reload cuga's tools   │  no restart needed
                     └──────────────────────────────┘
```

**Why three tiers?** Because **acquisition is a cost-quality tradeoff**. Catalog hits are sub-second and 100% reliable. OpenAPI generation is slower (LLM in the loop) but covers most public APIs. Browser tasks are slowest and most fragile, but they're the only way to reach sites that never published an API.

Whatever tier wins, the result is the same shape: a **ToolArtifact** on disk with manifest + code + probe outcome. The agent's tool universe is now `{previous tools} ∪ {new tool}` — and it persists across restarts.

---

## What we bring to the table — beyond vanilla cuga

| | **cuga alone** | **+ Chief of Staff & Toolsmith** |
|---|---|---|
| **Tool inventory** | fixed at deploy | grows with use, persists across restarts |
| **Authenticated APIs** | manual code change | per-tool vault + OAuth2 refresh built in |
| **Sites without APIs** | not supported | Playwright DSL fallback |
| **Vendor lock-in** | one planner, one model | swappable planner; swappable Coder (gpt-oss-120b ↔ Claude Sonnet) |
| **Auditability** | runtime decisions only | every acquired tool has manifest, source, probe history |
| **User control** | none over toolset | enable/disable any tool from UI; force gaps to test acquisition |
| **Observability** | tool calls invisible | per-message "via: tool_name" trail in chat |

Five durable platform properties:

1. **Self-extending.** The system gets stronger every time a user asks something new.
2. **Tiered acquisition.** Cheap path first, expensive path last — bounded LLM cost.
3. **Validate before expose.** A tool only ships if its probe succeeds. No silent broken tools.
4. **Credentials are first-class.** Vault + OAuth2 refresh + per-call secret injection means authenticated APIs aren't a special case.
5. **Swappable everything.** Planner, Coder, MCP servers — replace any one piece without touching the others.

---

## "Couldn't cuga do this inherently in code-mode?"

This is the most common pushback, and it deserves a direct answer.

**Yes — in principle, you could.** cuga's code-agent already writes Python that calls tools. You could extend its prompt to say *"if the tool you need doesn't exist, write the function inline and call it."* That works for a single turn.

We still split it out. Here's why:

| | **Inline in cuga** | **Separate Toolsmith** |
|---|---|---|
| **Lifetime of the tool** | dies when the chat turn ends | persists; serves all future users and sessions |
| **Per-tool validation** | runs once, in-conversation | probe-before-register, schema check, import allowlist, secret declaration |
| **Auditability** | code blob in a chat log | manifest with provenance, version, probe history, source URL |
| **Concurrency** | every user who hits the same gap re-builds it | first user pays the cost; everyone else gets the cached tool |
| **Specialization** | one model, one prompt, both jobs | tool-builder LLM separate from planner LLM (Claude Sonnet for codegen, gpt-oss for planning) |
| **Latency** | turn pays the build cost every time | once-per-tool amortized cost |
| **Swappability** | one big agent | swap Coder, swap planner, swap acquisition tier independently |
| **Failure isolation** | bad codegen breaks this conversation | bad codegen blocks one tool; rest keeps working |

**Separation of concerns is durable architecture.** cuga *answering questions* and Toolsmith *growing the toolbox* are two different jobs with two different optimization targets:

- cuga is optimized for **plan-quality and latency in this turn**.
- Toolsmith is optimized for **tool-correctness and reusability across all future turns**.

Conflating them makes both worse. The ops person who pages because "the chatbot is slow" and the platform person who needs to audit "what tools got added this week" are looking for different things — they should be able to look at different services.

There's also a real **cost** dimension. Tool-building can use a heavier reasoning model (Claude Sonnet) for accuracy; planning runs on cheaper inference (gpt-oss-120b). If it's all one agent, you can't make that tradeoff per job — every chat turn pays the heavier model's cost.

**One last point worth making**: this architecture isn't a bet against cuga. The orchestrator is just an HTTP coordinator. If a future cuga release ships native autonomous tool acquisition, we route gaps to *that* and retire Toolsmith — without rewriting the UI, the registry, the vault, or anything else. The seams are designed to make that swap painless. **We're not locked in; we're hedged.**

The honest answer to *"could cuga do this?"* is: **today, with effort, yes-ish — but you'd end up rebuilding most of Toolsmith inside it. The work is the work, regardless of where you put it.** Separation is what makes it possible to evolve each piece without re-litigating the whole system.

---

## What it looks like to a user

1. User: *"What's NVIDIA's stock price?"*
2. cuga has no finance tool → returns a gap.
3. Toolsmith finds **Finance MCP** in the catalog → mounts it → green card in the chat: **"Toolsmith built a tool"**.
4. cuga reloads with the new tool, returns the answer, with a small **`via: get_stock_quote`** footer.
5. Next time anyone asks about a stock, the tool is already there.

The user did nothing different. The toolbox is one tool richer. Forever.

---

## Why now

- **MCP** has standardized how models call tools — every meaningful API is going to ship an MCP server.
- **OpenAPI directories** (apis.guru, etc.) are now large and machine-readable enough that an LLM can synthesize a working client.
- **Playwright** is mature enough to be reliable for narrow, scripted browser tasks.
- **Open-weight code models** (gpt-oss-120b, Claude Sonnet 4.6) are good enough to write tool wrappers correctly with a single revise loop.

All four pieces only became real in the past 18 months. **The window to build the self-extending agent is open right now.**

---

## What we're asking for

- A green light to put this in front of a real internal user population (50–100 users) for 4 weeks.
- Specifically: the user community that already deals with the long tail of "I want to query X but there's no tool" problem.
- Outcome we're tracking: **growth in the persistent tool universe**, **acquisition success rate per tier**, and **median time from gap to working tool**.

If those numbers move the way we expect — and our internal trials suggest they will — this becomes the default agent platform pattern, not a one-off project.

---

*Built on top of cuga. Read more in `unified_experience.md` for the full architectural narrative, and `benchmark.md` for 70+ end-to-end test cases that exercise every tier of the system.*
