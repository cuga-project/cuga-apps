# Conversion Playbook: cuga-apps → portable skills

A self-contained spec for converting an app under
[`../cuga-apps/apps/<name>/main.py`](../cuga-apps/apps/) into a portable
[CUGA skill](https://github.com/anthropics/skills) at
[`cuga-skills/<name>/`](.).

This file is the artifact a fresh agent (or person) reads cold to do a
conversion with no other context. It defines:

- the **classification rules** (skill / hybrid / app) and the four boundary
  tests,
- the **dual-host skill format** (one `tools.py`, two invocation surfaces),
- the **per-app conversion recipe** (5 steps, ~15-30 min each),
- the **quality checklist** that must pass before declaring a skill done,
- the **testing protocol** the human runs to validate end-to-end,
- the **roster** of apps and which conversion archetype each follows.

The reference implementation is [`hiking_research/`](hiking_research/) —
read that as a worked example alongside this spec.

---

## 1. Classification: is this app a skill?

Answer four questions in order:

```
Q1. Does the agent need live data (HTTP, file I/O) the model
    doesn't already have in its weights?
    └─ NO  → Pure skill (SKILL.md only)
    └─ YES → continue

Q2. Can each user ask be served by a few short-lived function
    calls — i.e., no background loop, scheduler, or long pipeline?
    └─ NO  → App  (host owns the loop; conversion not viable)
    └─ YES → continue

Q3. Does state need to survive between asks, beyond what the agent
    can carry in context or push to CUGA's policy/memory layer?
    └─ NO  → Skill + tools.py
    └─ YES → continue

Q4. If you stripped the persistent state and any UI, would anything
    reusable remain (a "brain" portable to other hosts)?
    └─ YES → Hybrid: ship a skill for the brain, keep a thin app
              for storage/UI.
    └─ NO  → App: reasoning is incidental; the value is the loop.
```

### Sharp tests for each boundary

| Boundary | The question | Skill side | App side |
| --- | --- | --- | --- |
| Pure ↔ tools.py | "Could the agent succeed offline?" | yes | no |
| tools.py ↔ Hybrid | "If the user comes back tomorrow, should anything still be there?" | nothing | yes (pantry, watchlist, vector index) |
| Hybrid ↔ App | "Strip the persistence — what reasoning remains?" | reusable brain | nothing portable |
| tools.py ↔ App | "Does the host need to keep running between user actions?" | no | yes (cron, watcher, poller) |

---

## 2. Skill format (dual-host)

A portable skill is a folder with at most two files:

```
cuga-skills/<name>/
├── SKILL.md      # required — frontmatter + body
└── tools.py      # optional — only if the skill needs live data
```

### `SKILL.md` shape

Frontmatter (YAML):

```yaml
---
name: <skill_name>          # required, must match folder name
description: <one line>     # required, trigger-rich, mentions user verbs
requirements:               # optional, declares pip/npm deps
  - some-package>=1.0
---
```

Body sections, in order (omit any that don't apply):

1. **Title + framing** — one paragraph: what the skill does, what helpers exist.
2. **When to use this skill** — bulleted trigger phrases. The agent's routing depends on these.
3. **Tools provided** — a table mapping tool name → purpose, plus the
   "two invocation paths" snippet (see hiking_research for the canonical
   wording). Skip this section entirely for pure skills.
4. **Workflow** — numbered steps, referencing tools by name. Procedural,
   not prescriptive.
5. **Tone & failure modes** — what to say when tools error / return empty.
   Explicit "do not fabricate" guardrails.
6. **Output format** — a code-block schema showing the rendered output.
7. **Reference** (optional) — lookup tables, mapping enums, etc.

### `scripts/<name>.py` shape — stdlib CLI

This matches Anthropic's canonical [skills format](https://github.com/anthropics/skills):
a folder with `SKILL.md` + a `scripts/` directory of plain Python files. The
agent invokes them via `run_command` and parses JSON from stdout.

See [`hiking_research/scripts/hike_tools.py`](hiking_research/scripts/hike_tools.py)
or [`_template/scripts/hike_tools.template.py`](_template/scripts/hike_tools.template.py).

Three rules for the script:

1. **Public pure helpers.** Top-level functions like `geocode(place)` or
   `find_hikes(lat, lon, ...)`. No decorators. Stdlib only (or pip-deps
   declared in SKILL.md frontmatter as `requirements: [...]`).
2. **CLI dispatcher** inside `if __name__ == "__main__":`. Dispatches
   `argv[1]` to the matching helper, prints JSON to stdout, returns 0/1/2
   exit codes (0 = ok, 1 = runtime error, 2 = usage). Pass `-` for "skip
   this optional arg" when the next positional arg is non-empty.
3. **No langchain or framework imports.** The script must run anywhere
   Python 3 runs — inside a Docker sandbox, on a developer's laptop, in
   CI. If the script imports `langchain_core` or anything CUGA-specific,
   it's not portable.

### Why this format

- **Anthropic-compatible.** Matches the upstream
  [skills format](https://github.com/anthropics/skills) — your skill works
  in claude.ai, the Anthropic CLI, and any future host that honors the
  spec. No CUGA-specific extensions in the artifact.
- **Both CUGA hosts run the same script.** `cuga start demo_skills` (with
  OpenSandbox) uploads the folder and uses its built-in `run_command`.
  `cuga-skills-ui` (in-process, no Docker) provides its own host-side
  `run_command` that subprocesses on the local machine. Same SKILL.md,
  same script, same answer in both.

---

## 3. Per-app conversion recipe

Time budget: **15-30 min per skill+tools, 30-45 min per hybrid**. The
hybrid extra time is decisions, not code.

### Step 1 — Read for the brain

Open `cuga-apps/apps/<name>/main.py` and find the `_SYSTEM = """..."""`
block (or equivalent system-prompt constant). That text is ≈80% of the
final SKILL.md body. Strip:

- Demo-app preamble ("Welcome to X...")
- References to UI elements (chips, buttons, the demo URL)
- Any prompt-engineering hacks specific to the demo's LLM provider

Keep:

- "When to use" triggers
- Workflow logic (if-this-then-that)
- Tone rules
- Output format examples

### Step 2 — Identify what's brain vs plumbing vs tools

Scan the rest of `main.py` and bucket every function/constant:

| Category | Bucket | Action |
| --- | --- | --- |
| System prompt, decision rules, output shape | **Brain** | → SKILL.md body |
| HTTP calls, file parsing, computation | **Tools** | → scripts/&lt;name&gt;.py helpers |
| FastAPI routes, HTML, CORS, uvicorn launcher | **Plumbing** | drop |
| `_llm.py`, MCP bridge, port logic | **Plumbing** | drop |
| Module-level "last result" caches | **Plumbing** | drop |

Common patterns to look for:

- `from _mcp_bridge import load_tools` → these MCP tools become public functions in `scripts/<name>.py`, calling the underlying APIs directly via stdlib `urllib`.
- `app = FastAPI(...)` and route decorators → drop entirely; the host's `/ask` does this.
- `_HTML = """..."""` → drop; host owns the UI.
- `async def make_agent(): from cuga import CugaAgent ...` → drop; host instantiates the agent.

### Step 3 — Distill SKILL.md

Use [`_template/SKILL.template.md`](_template/SKILL.template.md) as a starting point. Fill in:

- **Frontmatter** `name`, `description`, optional `requirements: [...]`.
  Description trigger-rich, ≤2 lines. Test by reading it cold — would you
  know when to load this skill?
- **When to use**: 4-6 bullet triggers covering the real user phrasings.
- **Tools provided table**: one row per CLI subcommand. Copy-paste the
  "Example invocation" code block from
  [hiking_research/SKILL.md](hiking_research/SKILL.md) and adapt the path
  and arguments.
- **Workflow**: numbered steps. Reference subcommands by name. Don't say
  "press X" or "in the UI"; the skill is host-agnostic.
- **Tone & failure modes**: at minimum `"Never fabricate <X>"` and
  `"If <tool> returns empty, suggest <Y> before re-querying."` Plus
  `"If run_command isn't available, say so plainly."`
- **Output format**: a code-block schema with `<placeholders>`.

Keep the file under ~150 lines. If it's longer, you're being prescriptive.

### Step 4 — Build `scripts/<name>.py` (skip for pure skills)

Use [`_template/scripts/hike_tools.template.py`](_template/scripts/hike_tools.template.py) as a starting point.

For each network/file function in the original `main.py`:

1. Copy the underlying logic into a public top-level helper (e.g.
   `geocode(place)`, `find_hikes(lat, lon, ...)`). Strip module-level
   state — each helper is pure: input → output. **Stdlib only** when
   possible (`urllib` > `httpx`). The script must be importable and
   runnable in any Python environment, sandboxed or not.
2. Add a CLI dispatch case in `_main(argv)` matching the helper name.
   Print JSON to stdout on success; `{"error": "..."}` JSON on graceful
   failures; usage to stderr with exit 2 for bad arguments.
3. Add a usage line to `_USAGE`.

If the helpers need a pip dep, declare it in SKILL.md frontmatter as
`requirements: [pkg>=ver]`. The sandbox host installs deps before running.

### Step 5 — Drop everything else

Delete `requirements.txt` from the skill folder (deps live in SKILL.md
frontmatter). Delete any `__init__.py`. Skill folder = `SKILL.md` + (optional)
`scripts/`. That's it.

Update [`cuga-skills/README.md`](README.md) with a one-line entry in the
discovered-skills table.

---

## 4. Quality checklist

A skill is **done** when every box checks:

- [ ] **Description is trigger-rich.** Read it cold — do you know when to load this skill?
- [ ] **Frontmatter is valid.** `name` matches folder; `description` is one line; `requirements` set (empty list if stdlib-only).
- [ ] **CLI helpers documented.** Each subcommand listed in the Tools table with its inputs and return shape.
- [ ] **Workflow is procedural.** "If user mentions kids, pass `kid_friendly=true`" ✓; "Always greet the user warmly" ✗.
- [ ] **No host assumptions.** SKILL.md doesn't mention buttons, URLs, or specific UIs. Reference the script via the `/tmp/cuga_workspace/skills/<name>/` path that both hosts honor.
- [ ] **Failure modes named.** What to do when a tool errors / returns empty / has no permission. Including "if `run_command` isn't available, say so."
- [ ] **No fabrication.** Explicit guardrail against making up tool results.
- [ ] **CLI exits cleanly.** `0` on success, `1` on runtime error, `2` on usage. JSON-only on stdout. Errors to stderr.
- [ ] **No langchain or framework imports in `scripts/`.** Pure stdlib (or pip deps declared in frontmatter). The script must run anywhere Python 3 runs.
- [ ] **One golden question.** You ran the canonical user query end-to-end in `cuga-skills-ui` and got the right shape of answer.

The strongest test is **"works in two hosts."** If you only validated `cuga-skills-ui`, you're not done — `cuga start demo_skills` (with OpenSandbox) should serve the same answer for the same query, since both hosts upload the skill folder identically and `run_command` does the same thing.

---

## 5. Test plan (what the human runs after I finish a conversion)

This is what to run end-to-end to validate a freshly-converted skill.

### A — static checks (5s)

```bash
cd cuga-skills/<name>

# Frontmatter is valid YAML and has name + description
python3 -c "
import re
text = open('SKILL.md').read()
m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
assert m, 'no frontmatter'
import yaml; fm = yaml.safe_load(m.group(1))
assert fm.get('name'), 'missing name'
assert fm.get('description'), 'missing description'
print('frontmatter OK:', fm['name'])
"

# scripts/<name>.py imports cleanly (no langchain or framework deps)
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import <module> as t
print('helpers:', [n for n in dir(t) if not n.startswith('_')])
"
```

### B — CLI sanity (one minute)

For each subcommand, run the CLI with a trivial input:

```bash
python3 scripts/<name>.py <command> <minimal-args>           # → JSON on stdout
python3 scripts/<name>.py <command> 2>&1 >/dev/null; echo $?  # → 2 (usage error)
python3 scripts/<name>.py bogus 2>&1 >/dev/null; echo $?      # → 2 (unknown command)
```

Expect: JSON on stdout for happy-path, usage on stderr for errors, clean
exit codes.

### C — end-to-end via `cuga-skills-ui` (in-process host with subprocess `run_command`)

```bash
# in the venv where `cuga` is installed (e.g. cuga-agent-skills-branch/.venv)
cd /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills-ui
pip install -r requirements.txt          # idempotent
export ANTHROPIC_API_KEY=...              # or your provider of choice
python main.py --provider anthropic
# → http://127.0.0.1:28910
```

In the browser:

1. **Discovery** — the skill appears in the list with the correct
   description and a `+ scripts/` badge if it ships a `scripts/` directory.
2. **Import** — clicking Import copies the folder into both
   `./.cuga/skills/<name>/` (cuga's loader) and
   `/tmp/cuga_workspace/skills/<name>/` (so SKILL.md's `run_command` paths
   resolve).
3. **Golden question** — paste the canonical user query for this skill
   (see the per-app table below). The answer should:
   - Use the workflow from SKILL.md (e.g. geocode then find_hikes)
   - Cite real data (verifiable URLs, names that exist)
   - Render in the format SKILL.md prescribed
4. **Failure mode** — give the agent a query that should fail (e.g.
   "Hikes near Atlantis"). It should say so plainly, not fabricate.

### D — sandbox end-to-end via `cuga start demo_skills` (optional, one-time)

To validate the sandbox path with real OpenSandbox, install the skill
into the cuga checkout's project-local skills dir (or globally) — see
[QUICKSTART.md](QUICKSTART.md):

```bash
cp -R /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills/<name> \
      /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.cuga/skills/
```

Then start cuga (per QUICKSTART, use bare uvicorn to skip the
digital_sales preset):

```bash
# Terminal 1: opensandbox-server on :8080
# Terminal 2:
source /Users/anu/Documents/GitHub/cuga-agent-skills-branch/.venv/bin/activate
cd /Users/anu/Documents/GitHub/cuga-agent-skills-branch
DYNACONF_SKILLS__ENABLED=true \
DYNACONF_ADVANCED_FEATURES__OPENSANDBOX_SANDBOX=true \
DYNACONF_ADVANCED_FEATURES__ENABLE_SHELL_TOOL=true \
MCP_SERVERS_FILE=none \
python -m uvicorn cuga.backend.server.main:app --host 127.0.0.1 --port 7860
```

Open `:7860` and ask the same golden question. The agent should call
`load_skill(...)` followed by `run_command("python /tmp/cuga_workspace/skills/<name>/scripts/<file>.py …")`,
parse the JSON, and answer. Verify the answer matches Section C's.

You only need to do this once per skill (or once per conversion-pattern)
to confirm cross-host portability. After that, `cuga-skills-ui` testing is
enough day-to-day.

### E — reuse smoke test

Confirm the skill is genuinely portable. **Use copy, not symlink** — see the
note below about `Path.rglob` not following top-level symlinked skill dirs:

```bash
# install globally — COPY, not symlink
mkdir -p ~/.config/agents/skills
cp -R /Users/anu/Documents/GitHub/cuga-apps-may5/cuga-skills/<name> \
      ~/.config/agents/skills/<name>

# verify discoverable from a totally different cwd
cd /tmp && /path/to/cuga-agent-skills-branch/.venv/bin/python -c "
from cuga.backend.skills.loader import discover_skills
entries = discover_skills(None)
names = [e.name for e in entries]
print('Discovered:', names)
assert '<name>' in names
"
```

> **Symlinks don't work for global skill install (verified empirically).**
> CUGA's loader uses `Path.rglob('SKILL.md')`, which does NOT follow
> top-level symlinked directories on Python ≤ 3.12. If you symlink
> `~/.config/agents/skills/<name> → /repo/cuga-skills/<name>`, the loader
> silently sees zero skills. Use `cp -R` (or `rsync`) instead. Keep your
> source under git and re-copy on update.

---

## 6. App roster (what to convert)

Source apps live in [`../cuga-apps/apps/`](../cuga-apps/apps/). Each row
specifies the conversion archetype, the canonical golden question to
test with, and any tricky-case notes.

### Skill + `scripts/` archetypes (pure skill marked ★ — no `scripts/`)

These follow the playbook directly. ~15-30 min each.

| App | Subcommands (in `scripts/<name>.py`) | Golden question | Notes |
| --- | --- | --- | --- |
| ★ `code_reviewer` | (none) | Paste a 50-line Python function with subtle bug → "review this" | Pure skill — SKILL.md only. Smallest possible diff; good warm-up. |
| `webpage_summarizer` | `fetch_url` | "Summarize https://anthropic.com" | Single tool. Simplest tools.py example. |
| `wiki_dive` | `wiki_search`, `wiki_fetch` | "Deep dive on the Cambrian explosion" | Two tools. Wikipedia REST API. |
| `paper_scout` | `arxiv_search`, `semantic_scholar_lookup` | "Recent papers on retrieval-augmented generation" | Two tools, fan-out. Multi-source synthesis. |
| `arch_diagram` | `web_search` | "Mermaid diagram for a typical 3-tier web app" | Output is a Mermaid string; SKILL.md spec must be precise about the syntax. |
| `city_beat` | `weather`, `news`, `events`, `air_quality` | "What's happening in Boston today" | Multi-tool fan-out. |
| `travel_planner` | `geocode`, `flights`, `hotels`, `weather` | "5-day trip to Tokyo, mid-budget" | Heavy planning prompt. Long workflow. |
| `trip_designer` | `geocode`, `weather`, ... | (similar to travel_planner) | Same domain — tests how two skills coexist. |
| `ibm_docs_qa` | `ibm_docs_search`, `fetch_webpage` | "How do I create a Code Engine app from a Dockerfile" | Domain-constrained search. |
| `ibm_cloud_advisor` | `ibm_catalog_search`, `web_search` | "Which IBM service replaces AWS Lambda" | Catalog API + web. |
| `youtube_research` | `youtube_transcript` | "Summarize the Karpathy makemore video" | Drop the SQLite log. |
| `brief_budget` | `budget_classifier` | "Plan a $5k anniversary trip — flight to Iceland, 4 nights, dining" | Budget gate as a tool. |
| `api_doc_gen` | `parse_openapi`, `render_md` | "Generate docs for /tmp/spec.json" | Spec path is host input. |
| `box_qa` | `box_list`, `box_fetch` | "Find the Q3 forecast in my Box" | Box OAuth lives in host env (`os.getenv`). |
| `drop_summarizer` | `extract_pdf`, `extract_image` | "Summarize this PDF" (with file path) | Re-read source: it's upload-driven, not folder-watched. |

### Hybrid archetypes (skill + thin host)

These need an extra "decide the cut line" step. ~30-45 min each.

| App | Skill scope | Host scope | Cut-line note |
| --- | --- | --- | --- |
| `recipe_composer` | nutrition + recipe reasoning + nutrition_lookup tool | pantry storage | Push pantry into agent context per ask, OR keep in host. |
| `movie_recommender` | taste-profile reasoning + wikipedia tool | preference store | Ditto. |
| `deck_forge` | outline/slide-writing prompts + python-pptx tools | per-source-folder chromadb index | Each ask re-ingests, OR host owns persistent index. |
| `code_engine_deployer` | "classify each compose service" reasoning | actual `ibmcloud`/`docker` exec + log fetching with deploy gates | Deploy gates are app-shaped; classification is portable. |
| `server_monitor` | "interpret these metrics" reasoning | psutil collection loop + threshold notifications | The loop is intrinsically host. |

### Apps (not convertible — keep as-is)

These have value that **is** the persistent process. Don't try to
skill-ify them.

`smart_todo`, `voice_journal`, `newsletter`, `web_researcher`,
`ibm_whats_new`, `stock_alert`, `video_qa`,
`bird_invocable_api_creator`.

If CUGA later grows host primitives for "scheduled skill run" or "watch
folder, fire skill on event," 5-7 of these become convertible.

---

## 7. Conversion order

**Round 1 — pattern establishment (do these first).**

Pick the three that cover the three skill archetypes:

1. `code_reviewer` (★ pure skill) — validates SKILL.md alone shapes behavior.
2. `webpage_summarizer` (1 tool) — validates the simplest tools.py case.
3. `paper_scout` (2 tools, fan-out) — validates multi-tool routing.

After Round 1, the patterns are stable. Document any deviations from
this playbook in [hiking_research/](hiking_research/) or this file.

**Round 2 — bulk skill+tools (12 remaining).** Each takes ~15 min if
the archetype matches one from Round 1.

**Round 3 — hybrids (5).** Decide cut lines deliberately. Don't carry
the original UI into the skill.

---

## 8. Reference: hiking_research as a worked example

[`hiking_research/`](hiking_research/) is the reference implementation.
It exercises every part of this spec:

- Trigger-rich description with intent verbs.
- Two-subcommand `scripts/hike_tools.py` (`geocode`, `find_hikes`) with a
  CLI dispatcher that prints JSON.
- Public top-level helpers (`geocode`, `find_hikes`) — stdlib only, no
  langchain or framework imports.
- SKILL.md with the "Tools provided" table, the `/tmp/cuga_workspace/...`
  invocation example, and a Workflow that references each subcommand.
- "Do not fabricate" failure mode + "if `run_command` isn't available,
  say so" guard.
- Output schema in code-block form.
- `requirements: []` frontmatter (stdlib-only declared explicitly).

When in doubt, copy from there.
