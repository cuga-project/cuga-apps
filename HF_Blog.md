# Build real agentic apps on CUGA: `CUGA-apps` two dozen working examples on a lightweight agent harness

*Two dozen single-file apps that show how the CUGA harness works, and how the same agent runs governed inside IBM Sovereign Core.*

> **TL;DR** — If you've built agents before, you know the model is rarely the hard part. The work is wiring up tools, holding state together across a long task, adding guardrails, and growing from one agent to several without a rewrite. [CUGA](https://cuga.dev) (`pip install cuga`) is a small, open-source agent harness from IBM Research that handles that plumbing and stays configurable. To show what it feels like, we built [cuga-apps](https://github.com/cuga-project/cuga-apps): two dozen single-file apps, each a `CugaAgent` with a tool list and a system prompt. This article reads one end to end, names what the harness takes off your plate, and shows where the same agent runs governed in production. If you've written a FastAPI route, you can read every line.

Most agentic apps start with a week of plumbing before the agent does anything useful. You pick a framework, wire up a model client, write tool adapters, build some way to stream state to a UI, and somewhere in there you also decide what the agent is actually for. The interesting part arrives last.

[CUGA](https://github.com/cuga-project/cuga-agent) inverts that. Short for Configurable Generalist Agent, it's the open-source agent harness from IBM Research that handles the planning, the execution loop, the tool calls, and the state plumbing for you, so the part you write shrinks to a list of tools and a system prompt. To show what that feels like in practice, we built [cuga-apps](https://github.com/cuga-project/cuga-apps): 24 small, working apps, each a single FastAPI file wrapping one `CugaAgent`, from a movie recommender to an IBM Cloud architecture advisor. They exist to be read and copied.

This article walks through one of them, names what the harness takes off your plate, and shows where the same code goes when you need it governed for production. No new framework to learn first. If you've written a FastAPI route, you can read every line.

## Why a harness, not a framework

The fair question to ask of anything in this space is what it saves you from writing. CUGA's answer: the orchestration around a model that you'd otherwise rebuild every time.

It plans before it acts, then executes with a mix of tool calls and generated code (CodeAct). On a long task that runs twenty steps, the thing that breaks most agents is losing track of intermediate results and re-deriving them (often wrong) on the next turn; CUGA holds that state and runs a reflection step that can catch a bad call and re-plan instead of barreling ahead. That machinery is why it has topped agent benchmarks like AppWorld and WebArena rather than something you tune by hand.

You also set the cost/latency tradeoff from config rather than code: Fast, Balanced, and Accurate reasoning modes, with code execution in whatever sandbox you trust (local, Docker/Podman, or E2B cloud). Same agent definition, different dial.

None of the individual pieces is unique to CUGA. What's different is that they come pre-assembled, so you configure them instead of wiring them together. The API you touch is small — build a `CugaAgent` with a tool list and a prompt, then `await agent.invoke(...)`. Everything below that line is the harness.

Concretely, that's interchangeable tools (OpenAPI, MCP, and LangChain functions all bind the same way), long-horizon planning with variable management and self-correction (the machinery behind **#1 on [AppWorld](https://appworld.dev/)** and **[WebArena](https://webarena.dev/)**), declarative guardrails, multi-agent delegation over **A2A**, Docling-powered RAG, and one-env-var provider switching (`pip install cuga`, then OpenAI, watsonx, Ollama, and more) — each something you'd otherwise build yourself. The first word of the name does the work: *Configurable*; the hard parts are handled, so your job is just the task.

## One app, start to finish

Here's the IBM Cloud advisor — an agent that recommends real IBM Cloud services for an architecture. The whole thing fits in one file: a `main.py` with the agent factory, the tools, and the prompt, plus a small UI.

![Anatomy of the ibm_cloud_advisor cuga-app: the main.py file layout, an inline @tool (search_ibm_catalog) that calls the IBM Cloud Global Catalog API alongside an MCP web-search tool in one tool list, and a system prompt enforcing "catalog before recommendation."](cuga-apps/docs/architecture_app_anatomy_cloud_advisor.svg)

The whole agent is this:

```python
def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )
```

Four arguments. The model comes from a small factory (`create_llm`) that speaks to OpenAI, Anthropic, watsonx, RITS, LiteLLM, or Ollama depending on an environment variable. Nothing in the app code knows which model sits behind it. The `cuga_folder` is where this app keeps its state and any policies. The two arguments that carry the app are `tools` and `special_instructions`.

The tools mix a local function with a hosted one:

```python
def _make_tools():
    from langchain_core.tools import tool

    @tool
    def search_ibm_catalog(query: str) -> str:
        """Search the IBM Cloud Global Catalog for real IBM Cloud services.
        Always call this before recommending services to verify they exist."""
        ...  # hits the catalog API, returns JSON

    from _mcp_bridge import load_tools
    web_tools = load_tools(["web"])

    return [search_ibm_catalog, *web_tools]
```

There's a pattern here that holds across every app: a split between MCP tools and inline tools. Generic, stateless capabilities come from shared MCP servers; `load_tools(["web"])` pulls in web search without you hosting anything. Anything specific to this app gets defined inline as a normal Python function, like `search_ibm_catalog`, whose docstring is what the agent reads to decide when to call it. You write the one tool that's yours and borrow the rest.

The system prompt does the steering, and it reads like a procedure rather than a personality. The cloud advisor's prompt tells the agent to search the catalog before naming any service, recommend three to seven services with each one's role in the design, and never invent service names. That last rule earns its keep: an agent recommending IBM Cloud services that don't exist is worse than no agent, so the prompt forces every recommendation through a catalog lookup first. Prompts written as ordered steps with explicit "don't make things up" rules behave; prompts written as personas wander.

That's the app. A tool, a procedure, four lines of constructor. The FastAPI routes around it are ordinary web code: the browser posts a question to `/ask`, and the live panel polls a `/session/{thread_id}` endpoint for state. There's no database; state is a per-`thread_id` Python dict that only the agent writes to, through its tools. The moment the agent calls a tool mid-run, the panel redraws. The UI isn't a second copy of the logic; it's a view onto state the agent mutated.

## The convention that does the heavy lifting

One detail is easy to skip and turns out to be load-bearing: every inline tool returns the same small envelope. Success looks like `{"ok": true, "data": {...}}`; failure looks like `{"ok": false, "code": "...", "error": "..."}`.

It looks like boilerplate. It isn't. CUGA's planner handles a *declared* failure gracefully ("geocoding didn't return anything, skip that section and keep going") and chokes on an *undeclared* one, where a raw stack trace bubbles up mid-plan and the run derails. Across the apps, the ones that worked reliably were the ones whose tools never threw a bare exception at the agent. A boring convention, but it's the difference between an agent that recovers and one that face-plants.

The split above only pays off because the generic half is already running somewhere. The capabilities the apps reach for over and over — web search, Wikipedia/arXiv, geocoding and weather, finance quotes, and a few more — live in **7 public MCP servers (36 tools)** hosted on IBM Code Engine, no auth required. A small bridge resolves their URLs automatically, and the [live gallery](https://cuga-apps-ui.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/) ships an **MCP Tool Explorer** to call any of them from a form before you wire it into an agent.

## A library, not a demo

The reason there are two dozen of these matters more than any single one. Once you've read the cloud advisor, you've read all of them, because they share the skeleton. The movie recommender swaps the IBM catalog tool for the `knowledge` MCP server; the web researcher leans almost entirely on `web`. Same shape, different tools and prompt.

Before you clone anything, you can [click through every app in the live gallery](https://cuga-apps-ui.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/): the umbrella UI tiles all of them behind a launch button, so you can poke at the cloud advisor or the movie recommender in a browser first.

So cuga-apps works as a catalog of starting points, which is the real reason to care about it. Want an agent that reads documents? There's one. Want an event-driven pipeline instead of a chat app? The newsletter and drop-summarizer apps are built that way. Each app leans on a different capability (tool composition, stateful tools, web grounding, citation tracking, code synthesis), so between them they map out most of what the harness can do, and whatever you're building, one of them already exercises the piece you need. You clone the repo, find the app closest to your idea, and edit its tool list and prompt; `HOW_TO_BUILD_AN_APP_FAST.md` and `ADDING_AN_APP.md` walk through exactly that. A few apps were even generated by handing a coding assistant a single spec file (`cuga_external_app_spec.md`) and a one-line brief, which tells you how repeatable the shape is — regular enough for a model to reproduce means regular enough for you to learn.

So what can you actually build on the pattern? The apps already fan out across families. A **research-and-knowledge** cluster pulls sourced answers out of the open web and the literature — Paper Scout ranks arXiv and Semantic Scholar papers by citation count, Wiki Dive and Web Researcher do cited synthesis, YouTube Research works from transcripts. An **everyday-productivity** cluster covers the small useful things — a daily city briefing, a multi-day travel planner, a pantry-driven recipe composer, trail discovery for a weekend hike. A **document-and-media** cluster ingests PDFs, audio, and video and answers over them with RAG. There's an **ops** corner watching live system metrics and market prices, an **enterprise** example answering questions from real IBM product documentation, and **Ouroboros**, a seven-agent lead-gen system that's the one to open when you want the multi-agent shape. Between them they exercise tool composition, stateful tools, web grounding, citation tracking, RAG over a private corpus, code synthesis, and self-correction — so whatever you're building, one app already exercises the piece you need.

Two honest caveats before you clone. The real catalog lives in the inner `cuga-apps/cuga-apps/apps/` directory, not the outer one, which trips people up on first read. And not every app is equally polished: the umbrella UI tags apps "ship-ready," "for-later," or "exploratory," and the for-later ones aren't wired for a clean unattended run yet. The UI defaults to the ship-ready filter and lets you switch between those tags, so the polished set is what you see first. Start from a ship-ready app like the cloud advisor or the movie recommender and you'll have a working baseline.

## When the laptop version isn't enough

A demo agent that searches a catalog is low-stakes. Point the same pattern at something that writes files, runs shell commands, or touches production, and the question changes: how do you stop it doing something you'll regret?

CUGA answers this in the runtime, not in a wrapper you add afterward. The open-source agent ships a policy system, and you attach policies to the same agent object:

```python
await agent.policies.add_intent_guard(
    name="Block force-push",
    keywords=["--force", "--no-verify"],
    response="Blocked: destructive git flags are not permitted.",
)
```

That's an Intent Guard, one of six policy types, each answering a question a team asks before letting an agent loose:

- **Intent Guard** — can it refuse a request outright?
- **Tool Approval** — can it pause for a human before a risky tool runs?
- **Tool Guide** — can I steer how a specific tool gets used without rewriting it?
- **Playbook** — can I pin a known-good procedure for a recurring task?
- **Output Formatter** — can I force the final response into a required shape?

A sixth type, `CustomPolicy`, is the escape hatch when none of those fit. Timing is worth getting right, because it isn't all one stage: an Intent Guard checks the request before the agent picks a tool, Tool Approval runs *after* the agent has generated its code and inspects which tools that code uses, and Output Formatter fires only once the final message exists. Triggers go past keyword matching too: they're held in a `sqlite-vec` store and matched semantically, so a policy fires on what the user *means*, not just on an exact keyword. Match on semantic similarity, on agent state, or on a specific tool firing. The policies themselves live in that `.cuga` folder from the constructor, versioned next to the code rather than drifting in a separate config.

## Growing past one agent

Two extensions matter once an app outgrows a single chat loop.

When one agent would drown in its own context (too many tools, too much evidence to keep straight), you split the work. A `CugaSupervisor` delegates to specialist `CugaAgent`s, each with its own tools, prompt, and isolated context, and the supervisor only ever reasons about which specialist to hand a subtask to. Its planning surface stays small no matter how many tools sit underneath, and a flaky tool fails one delegation instead of the whole run. A specialist doesn't even have to be local; it can be an external agent reached over A2A, delegated to the same way. Adding a capability means adding a specialist, not rewriting a coordinator.

The other extension packages know-how rather than tools: Agent Skills, a folder with a `SKILL.md` playbook the agent pulls into context only when a task calls for it, so one prompt isn't carrying everything the agent might ever need to know. Both keep the same building blocks (tools, prompts, state, policies), just composed a level up.

## The moat: governed by construction

It's worth stepping back to ask where CUGA sits relative to everything else you could build an agent on, because that positioning is what makes the redeploy story in the next section real rather than aspirational. Most of the field falls into two camps. There are minimal developer libraries, where the primitives are good but you assemble the governance — identity, audit, policy, lifecycle, approvals — yourself. And there are broad-access personal-agent runtimes, fast to demo precisely because they start with reach into your filesystem, shell, and browser, where the work becomes *constraining* access that already exists.

CUGA is built for a third category: an enterprise-oriented harness where policy-as-code, human-in-the-loop approval, durable state, self-hosting, and data residency are first-class from the first line, not bolted on later. That flips the direction of the hard work. Starting from a personal-agent runtime, you *govern upward* — retrofitting controls onto something built for access, which tends to leave you maintaining a brittle external overlay or a long-lived internal fork, both expensive forever. Starting from CUGA, you *harden execution downward*: the control plane is already there, so the remaining work is tightening the sandbox around the few side-effecting tools, not inventing the governance around them. That's the moat — not any single feature, but that the governed path is the default one and the ungoverned shortcuts are the ones you have to opt into. It's also why the same agent definition carries from a laptop to a locked-down deployment without a rewrite, which is exactly where this goes next.

## Where the same agent ends up

Here's the payoff, and the reason any of this is built the way it is. Because the harness is small, open source, model-agnostic, and already governs itself, the agent you wrote on your laptop is the same agent that runs in a locked-down deployment. You don't port it. You redeploy it.

That's the foundation [IBM Sovereign Core](https://www.ibm.com/products/sovereign-core) builds on, and it's where we took CUGA next. [We wrote about the details separately](https://community.ibm.com/community/user/blogs/shikha-srivastava1/2026/04/30/open-by-design-generalist-and-prebuilt-agents-in-t), but the short version: Sovereign Core runs CUGA agents under what we call Boundary Isolation: data, control plane, and execution engine inside the same logical boundary, with agents running in transient, isolated containers in the tenant's own workspace. The model runs there too. Deployments default to `gpt-oss-120b` running fully air-gapped within your infrastructure, and tools reach only private VNETs with per-tool approval. Every reasoning step emits OpenTelemetry traces into a Grafana Tempo backend that stays in-tenant, with no telemetry phoning home. Nothing leaves the boundary.

The agent definition doesn't change to get there; the deployment around it does. And the reason that's possible is everything above — capability, policy, and model choice all live in a runtime you can read. That's the bet we made building it: when an agent's runtime is a black box, sovereignty is a promise, but when it's open code, sovereignty is something you can check. The apps you cloned and the agent you wrote are the same open runtime that claim rests on.

The developer takeaway stands on its own, though. An agentic app can be one file you hold in your head. The tools and the prompt are the only parts you really write. The apps are a library to learn from, not a sealed demo. And when the stakes rise, the governance is already in the runtime — you don't rebuild the agent to make it safe.

## Next steps

Clone the repo and run an app. The hosted MCP servers mean you don't need third-party keys, just an LLM provider. Point it at a local Ollama model and there's no API cost at all:

```bash
git clone https://github.com/cuga-project/cuga-apps.git
cd cuga-apps/cuga-apps
CUGA_TARGET=ce python apps/launch.py   # use hosted MCP servers; no extra keys
```

Then open `apps/ibm_cloud_advisor/main.py` and read it end to end — it's the clearest example of the inline-tool-plus-MCP pattern. Change the system prompt, add a tool, and watch the behavior shift. The MCP Tool Explorer lists every hosted tool with a form to call it directly, which is a quick way to check the plumbing before wiring a tool into an agent.

If you build something on the pattern, the apps live in the open at [github.com/cuga-project/cuga-apps](https://github.com/cuga-project/cuga-apps), the harness at [cuga-agent](https://github.com/cuga-project/cuga-agent), and the project home is [cuga.dev](https://cuga.dev). Open an issue, file a PR, or drop in your own app — the repo is built to be added to.

## Resources

- [cuga-apps](https://github.com/cuga-project/cuga-apps) — the apps, MCP servers, and UI in this article
- [Live app gallery + MCP Tool Explorer](https://cuga-apps-ui.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/) — every app behind a launch button, plus a form to call each hosted MCP tool directly
- [cuga-agent](https://github.com/cuga-project/cuga-agent) — the CUGA runtime and policy system
- [cuga.dev](https://cuga.dev) — CUGA project home (`pip install cuga`)
- [Open by Design: Generalist and Pre-Built Agents in the Sovereign Core](https://community.ibm.com/community/user/blogs/shikha-srivastava1/2026/04/30/open-by-design-generalist-and-prebuilt-agents-in-t) — IBM Community post on how CUGA runs inside Sovereign Core (Srivastava, Marreed, Thomas, April 2026)
- [IBM Sovereign Core](https://www.ibm.com/products/sovereign-core) — product page
