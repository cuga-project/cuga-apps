# Build real agentic apps using CUGA: two dozen working examples on a lightweight harness

> **TL;DR** — Building an agent is mostly plumbing: tools, state, guardrails, scaling from one agent to many. CUGA (pip install cuga), short for Configurable Generalist Agent, the Agent Harness for the Enterprise from IBM handles that, so you write just a tool list and a prompt. We built two-dozen single-file apps to prove it. Read one end to end here, then see how the same agent runs sovereign and governed in production without a rewrite.

Most agentic apps start with a week of plumbing before the agent does anything useful. You pick a framework, wire up a model client, write tool adapters, build some way to stream state to a UI, and somewhere in there you also decide what the agent is actually for. The interesting part arrives last.

[CUGA](https://github.com/cuga-project/cuga-agent) inverts that. It's the open-source agent harness from IBM that handles the planning, the execution loop, the tool calls, and the state plumbing for you. What's left is the part that's actually yours: which tools the agent can reach, and what you tell it to do. To show what that feels like in practice, we built [cuga-apps](https://github.com/cuga-project/cuga-apps): two dozen small, working apps, each a single FastAPI file wrapping one `CugaAgent`, from a movie recommender to an IBM Cloud architecture advisor. They exist to be read and copied. You can [click through the live gallery](https://huggingface.co/spaces/ibm-research/cuga-apps).


This article walks through one of them, names what the harness takes off your plate, and shows where the same code goes when you need it governed for production. No new framework to learn first. If you've written a FastAPI route, you can read every line.

## Why a harness, not a framework

The fair question to ask of anything in this space is what it saves you from writing. CUGA's answer: the orchestration around a `model` that you'd otherwise rebuild every time.

It plans before it acts, then executes with a mix of tool calls and generated code (CodeAct). On a long task that runs twenty steps, the thing that breaks most agents is losing track of intermediate results and re-deriving them (often wrong) on the next turn; CUGA holds that state and runs a reflection step that can catch a bad call and re-plan instead of barreling ahead. That machinery is why it has topped agent benchmarks like AppWorld and WebArena rather than something you tune by hand.

You also set the cost/latency tradeoff from config rather than code: Fast, Balanced, and Accurate reasoning modes, with code execution in whatever sandbox you trust (local, Docker/Podman, or E2B cloud). Same agent definition, different dial. That dial matters more than it sounds. Most harnesses assume a frontier model sits underneath and lean on it to recover when a plan goes sideways; CUGA does that work itself. The planning, the reflection step, the variable-tracking that keeps a long run on course — that's the harness carrying load the model would otherwise have to, which is what lets a smaller open-weight model hold up where it normally wouldn't. It's why the hosted apps run on gpt-oss-120b rather than a frontier API. Running the biggest model you can call is the usual bet; CUGA's is that a smaller open one is enough.

None of the individual pieces is unique to CUGA. What's different is that they come pre-assembled, so you configure them instead of wiring them together. The API you touch is small — build a `CugaAgent` with a tool list and a prompt, then `await agent.invoke(...)`. Everything below that line is the harness.

Concretely, that's interchangeable tools (OpenAPI, MCP, and LangChain functions all bind the same way), long-horizon planning with variable management and self-correction (the machinery behind **#1 on [AppWorld](https://appworld.dev/)** from 07/25 - 02/26 and **[WebArena](https://webarena.dev/)**  from 02/25 - 09/25), declarative guardrails, multi-agent delegation over **A2A**, Docling-powered RAG, and one-env-var provider switching (`pip install cuga`, then OpenAI, watsonx, Ollama, and more) — each something you'd otherwise build yourself. The first word of the name does the work: *Configurable*; the hard parts are handled, so your job is just the task.

## One app, start to finish

Here's the IBM Cloud advisor — an agent that recommends real IBM Cloud services for an architecture. The whole thing fits in one file: a `main.py` with the agent factory, the tools, and the prompt, plus a small UI.
 

![Anatomy of the ibm_cloud_advisor cuga-app: the main.py file layout, an inline @tool (search_ibm_catalog) that calls the IBM Cloud Global Catalog API alongside an MCP web-search tool in one tool list, and a system prompt enforcing "catalog before recommendation."](https://cdn-uploads.huggingface.co/production/uploads/649d9ad1500fd8d51a675a93/UWUOaGwQ7pCVGWT7-Vbg6.png)
 
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

Four arguments. The model comes from a small factory (`create_llm`) that speaks to OpenAI, Anthropic, watsonx, LiteLLM, or Ollama depending on an environment variable. Nothing in the app code knows which model sits behind it. The `cuga_folder` is where this app keeps its state and any policies. The two arguments that carry the app are `tools` and `special_instructions`.

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

The cloud advisor's prompt tells the agent to search the catalog before naming any service, recommend three to seven services with each one's role in the design, and never invent service names. That last rule earns its keep: an agent recommending IBM Cloud services that don't exist is worse than no agent, so the prompt forces every recommendation through a catalog lookup first. Prompts written as ordered steps with explicit "don't make things up" rules behave; prompts written as personas wander.

That's the app. A tool, a procedure, four lines of constructor. The FastAPI routes around it are ordinary web code: the browser posts a question to `/ask`, and the live panel polls a `/session/{thread_id}` endpoint for state. There's no database; state is a per-`thread_id` Python dict that only the agent writes to, through its tools. The moment the agent calls a tool mid-run, the panel redraws. The UI isn't a second copy of the logic; it's a view onto state the agent mutated.

## The convention that does the heavy lifting

One detail is easy to skip and turns out to be load-bearing: every inline tool returns the same small envelope. Success looks like `{"ok": true, "data": {...}}`; failure looks like `{"ok": false, "code": "...", "error": "..."}`.

It looks like boilerplate. It isn't. CUGA's planner handles a *declared* failure gracefully ("geocoding didn't return anything, skip that section and keep going") and chokes on an *undeclared* one, where a raw stack trace bubbles up mid-plan and the run derails. Across the apps, the ones that worked reliably were the ones whose tools never threw a bare exception at the agent. A boring convention, but it's the difference between an agent that recovers and one that face-plants.

The split above only pays off because the generic half is already running somewhere. The capabilities the apps reach for over and over — web search, Wikipedia/arXiv, geocoding and weather, finance quotes, and a few more — live in **7 public MCP servers (36 tools)** hosted on IBM Code Engine, no auth required. A small bridge resolves their URLs automatically, and the [live gallery](https://huggingface.co/spaces/ibm-research/cuga-apps) ships an **MCP Tool Explorer** to call any of them from a form before you wire it into an agent.

## A library, not a demo

The reason there are two dozen polished apps matters more than any single one: once you've read the cloud advisor, you've read all of them. They share a skeleton — the movie recommender swaps the IBM catalog tool for the `knowledge` MCP server, the web researcher leans almost entirely on `web` — so cuga-apps is really a catalog of starting points. You clone the repo, find the app closest to your idea, and edit its tool list and prompt ([HOW_TO_BUILD_AN_APP_FAST.md](https://github.com/cuga-project/cuga-apps/blob/main/cuga-apps/docs/HOW_TO_BUILD_AN_APP_FAST.md) and [ADDING_AN_APP.md](https://github.com/cuga-project/cuga-apps/blob/main/cuga-apps/docs/ADDING_AN_APP.md) walk through exactly that). A few apps were even generated by handing a coding assistant one spec file and a one-line brief — regular enough for a model to reproduce means regular enough for you to learn. You can [click through every one in the live gallery](https://huggingface.co/spaces/ibm-research/cuga-apps) before cloning anything.

They also fan out across families, so whatever you're building, one app already exercises the piece you need. There's a research cluster (Paper Scout ranks arXiv papers by citation count; Wiki Dive and Web Researcher do cited synthesis), an everyday-productivity set (city briefings, travel, recipes, trails), a document-and-media group that does RAG over PDFs, audio, and video, an ops corner watching live metrics, and an enterprise example over real IBM product docs. Ouroboros is a seven-agent lead-gen system; open it for the multi-agent shape. And Meetup Finder drives headless Chromium through Playwright to pull structured events off Meetup, Luma, and Eventbrite (all of which killed their public search APIs); open it for browser automation, which is where CUGA started and the muscle behind its strong WebArena results.

Two caveats before you clone. The real catalog lives in the inner `cuga-apps/cuga-apps/apps/` directory, not the outer one. And not every app is equally polished, so the UI tags them "showcase" or "additional apps" and defaults to "showcase"; start from the cloud advisor or movie recommender for a working baseline.

## Keeping your agent within the boundaries

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

For a working example, open [Ouroboros](https://github.com/cuga-project/cuga-apps/tree/main/cuga-apps/apps/ouroboros) — a seven-agent lead-gen app that attaches three policies (an intent guard, a tool guide, and an output formatter) to its supervisor, so it's the one app that demos governance and the multi-agent shape in the same file.

## Growing past one agent

Two extensions matter once an app outgrows a single chat loop. When one agent would drown in its own context (too many tools, too much evidence to keep straight), you split the work. A `CugaSupervisor` delegates to specialist `CugaAgent`s, each with its own tools, prompt, and isolated context, and the supervisor only ever reasons about which specialist to hand a subtask to. Its planning surface stays small no matter how many tools sit underneath, and a flaky tool fails one delegation instead of the whole run. A specialist doesn't even have to be local; it can be an external agent reached over A2A, delegated to the same way. Adding a capability means adding a specialist, not rewriting a coordinator.

The other extension packages know-how rather than tools: Agent Skills, a folder with a `SKILL.md` playbook the agent pulls into context only when a task calls for it, so one prompt isn't carrying everything the agent might ever need to know. Both keep the same building blocks (tools, prompts, state, policies), just composed a level up.

Ouroboros, the lead-gen app from earlier makes this pattern concrete. It has a supervisor over seven specialists (scout, site auditor, voice-of-customer, person finder, stack scanner, revenue estimator, and a pitch-email writer that synthesizes). Each specialist is one skill loaded into a `CugaAgent`, and the supervisor calls it through an auto-generated `delegate_to_<name>` tool. Adding an eighth is a one-line factory, not a coordinator rewrite. Read its `main.py` and `ARCHITECTURE.md` if you want the multi-agent shape end to end.

There's a third extension, and it points back at the skills themselves. With [ALTK-Evolve](https://agenttoolkit.github.io/altk-evolve/), CUGA's on-the-job learning framework, an agent refines a skill from its own runs so a task done today makes tomorrow's faster and more accurate. The `SKILL.md` a specialist loads ends up holding what the agent learned on top of what you wrote. Same building blocks, except now using one teaches the next. The thing you stop doing is re-prompting through a problem you already solved last week.

## Governed by construction

Where governance lives in the stack shapes how the production story goes. A minimal agent library hands you good primitives and leaves the governance (policy, approvals, audit, identity) for you to assemble. CUGA takes the other path: policy, human-in-the-loop approval, the `.cuga` state folder, and self-hosting are part of the harness from the first line, not a layer you add later.

That changes the direction of the work when you take an agent to production. You're not retrofitting controls onto something built for open access; the control plane is already there. The governed path is the default, and the ungoverned shortcuts are the ones you opt into. So the remaining job is narrow: tighten the sandbox around the few tools that actually touch the outside world, rather than invent the governance around them

## Where the same agent ends up

Here's the payoff, and the reason any of this is built the way it is. Because the harness is small, open source, model-agnostic, and already governs itself, the agent you wrote on your laptop is the same agent that runs in a locked-down deployment. You don't port it. You redeploy it.

That's the foundation [IBM Sovereign Core](https://www.ibm.com/products/sovereign-core) builds on, and it's where we took CUGA next. [We wrote about the details separately](https://community.ibm.com/community/user/blogs/shikha-srivastava1/2026/04/30/open-by-design-generalist-and-prebuilt-agents-in-t), but the short version: Sovereign Core runs CUGA agents under what we call Boundary Isolation: data, control plane, and execution engine inside the same logical boundary, with agents running in transient, isolated containers in the tenant's own workspace. The model runs there too. Deployments default to `gpt-oss-120b` running fully air-gapped within your infrastructure, and tools reach only private VNETs with per-tool approval. Every reasoning step emits OpenTelemetry traces into a Grafana Tempo backend that stays in-tenant, with no telemetry phoning home. Nothing leaves the boundary.

The agent definition doesn't change to get there; the deployment around it does. And the reason that's possible is everything above — capability, policy, and model choice all live in a runtime you can read. That's the bet we made building it: when an agent's runtime is a black box, sovereignty is a promise, but when it's open code, sovereignty is something you can check. The apps you cloned and the agent you wrote are the same open runtime that claim rests on.

The developer takeaway stands on its own, though. An agentic app can be one file you hold in your head. The tools and the prompt are the only parts you really write. The apps are a library to learn from, not a sealed demo. And when the stakes rise, the governance is already in the runtime — you don't rebuild the agent to make it safe.

## Next steps

Clone the repo and run an app. The hosted MCP servers mean you don't need third-party keys, just an LLM provider. The apps in this article run on the open-weights **`gpt-oss-120b`** — the same model the hosted gallery and our Sovereign Core deployments use — but because the model is a one-line swap (`create_llm` reads a single env var), you can point any app at OpenAI, Anthropic, watsonx, or a local Ollama model with no code change, and at a local model there's no API cost at all:


Start by reviewing our Quick Start Guide [here](https://github.com/cuga-project/cuga-apps#1--an-inline-tools-only-app-fastest-path). If you'd like to set up all the applications, ensure Docker is running and then follow the steps below.

```bash
git clone https://github.com/cuga-project/cuga-apps.git
cd build
cp .env.example .env          # set your LLM provider + key; add TAVILY_API_KEY /
                              # OPENTRIPMAP_API_KEY / ALPHA_VANTAGE_API_KEY for the
                              # apps that use them
docker compose up --build     # first build is large (cuga + Chromium + MCP deps)
# open http://localhost:8080
```


Then open `apps/ibm_cloud_advisor/main.py` and read it end to end — it's the clearest example of the inline-tool-plus-MCP pattern. Change the system prompt, add a tool, and watch the behavior shift. The MCP Tool Explorer lists every hosted tool with a form to call it directly, which is a quick way to check the plumbing before wiring a tool into an agent.

So try it. `pip install cuga`, clone [cuga-apps](https://github.com/cuga-project/cuga-apps), and run an app — or just [click through the live gallery](https://huggingface.co/spaces/ibm-research/cuga-apps) first. The harness lives at [cuga-agent](https://github.com/cuga-project/cuga-agent) and the project home is [cuga.dev](https://cuga.dev). If something breaks, an app misbehaves, or you have an idea, we want to hear it: open an issue, file a PR, drop in your own app, or just reach out — the repo is built to be added to, and we read everything that comes in.

## Resources

- [cuga-apps](https://github.com/cuga-project/cuga-apps) — the apps, MCP servers, and UI in this article
- [cuga-apps/apps](https://github.com/cuga-project/cuga-apps/tree/main/cuga-apps/apps) — the two dozen polished single-file agent apps (the inner catalog; clone from here)
- [cuga-apps/mcp_servers](https://github.com/cuga-project/cuga-apps/tree/main/cuga-apps/mcp_servers) — the shared MCP servers (web, knowledge, geo, finance, code, text, …) the apps borrow
- [Live app gallery + MCP Tool Explorer](https://huggingface.co/spaces/ibm-research/cuga-apps) — every app behind a launch button, plus a form to call each hosted MCP tool directly
- [cuga-agent](https://github.com/cuga-project/cuga-agent) — the CUGA runtime and policy system
- [cuga.dev](https://cuga.dev) — CUGA project home (`pip install cuga`)
- [Open by Design: Generalist and Pre-Built Agents in the Sovereign Core](https://community.ibm.com/community/user/blogs/shikha-srivastava1/2026/04/30/open-by-design-generalist-and-prebuilt-agents-in-t) — IBM Community post on how CUGA runs inside Sovereign Core (Srivastava, Marreed, Thomas, April 2026)
- [IBM Sovereign Core](https://www.ibm.com/products/sovereign-core) — product page
  
