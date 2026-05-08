# cuga-skills

A library of reusable [agent skills](https://github.com/anthropics/skills)
in the canonical Anthropic format. Each subdirectory is a self-contained
skill: a `SKILL.md` (frontmatter + markdown playbook) plus an optional
`scripts/` directory of plain stdlib Python the agent invokes via
`run_command`.

## Layout

```
cuga-skills/
├── README.md
├── QUICKSTART.md              # how to run with cuga + opensandbox
├── CONVERSION_PLAYBOOK.md     # how to convert cuga-apps → skills
├── _template/                 # skeleton SKILL.md + scripts/ for new skills
└── <skill_name>/
    ├── SKILL.md               # required — frontmatter + body
    └── scripts/               # optional — stdlib Python the agent calls via run_command
        └── <name>.py
```

- **Running it** → [QUICKSTART.md](QUICKSTART.md) — two terminals, watsonx,
  bare uvicorn (skips the digital_sales preset). Read this first.
- **Authoring new skills** → [CONVERSION_PLAYBOOK.md](CONVERSION_PLAYBOOK.md)
  — classification rules, skill format, per-app recipe, quality checklist,
  test protocol.

Discovered skills:

| Skill | Description | Keys |
| --- | --- | --- |
| [`api_doc_gen`](api_doc_gen/SKILL.md) | Generate human-readable API docs from a local OpenAPI / Swagger spec — endpoints, $ref expansion, realistic curl examples. | — |
| [`arch_diagram`](arch_diagram/SKILL.md) | Generate Mermaid.js architecture diagrams from natural-language system descriptions, with optional web search for unfamiliar systems. | TAVILY (opt) |
| [`box_qa`](box_qa/SKILL.md) | Browse a Box folder via JWT auth and answer questions over PDFs/DOCX/XLSX/PPTX/TXT/MD/CSV with file-cited answers. | BOX_CONFIG_PATH |
| [`brief_budget`](brief_budget/SKILL.md) | Goal-shaped research analyst with a stated tool-call budget — you decide decomposition + tool mix; covers academic, encyclopedic, and web sources. | TAVILY (opt) |
| [`city_beat`](city_beat/SKILL.md) | One-screen city briefing — weather, news, encyclopedia background, optional attractions and crypto spotlight. | TAVILY · OPENTRIPMAP (opt) |
| [`code_reviewer`](code_reviewer/SKILL.md) | Pure skill — structured code review (severity-ranked issues, suggestions, insights, metrics). No scripts. | — |
| [`drop_summarizer`](drop_summarizer/SKILL.md) | TL;DR + key points for a local document path (.txt, .md, .csv, .pdf, .docx, .pptx, .xlsx). | — |
| [`hiking_research`](hiking_research/SKILL.md) | Discover, filter, and evaluate hiking trails near any location using OpenStreetMap. | — |
| [`ibm_cloud_advisor`](ibm_cloud_advisor/SKILL.md) | Recommend real IBM Cloud services for a use case via the public Global Catalog, with `ibmcloud` CLI commands. | TAVILY (opt) |
| [`ibm_docs_qa`](ibm_docs_qa/SKILL.md) | Answer IBM Cloud / IBM product questions by searching real IBM docs and synthesising sourced answers. | TAVILY |
| [`ibm_whats_new`](ibm_whats_new/SKILL.md) | Track and digest IBM Cloud release notes / "What's New" announcements for named services. Same tools as `ibm_docs_qa`, recency-biased. | TAVILY |
| [`lead_hunter`](lead_hunter/SKILL.md) | Sales-dev scout — ranked board of independent local businesses that would benefit from a conversational AI agent, with deep-dive evidence and tailored cold emails. | TAVILY |
| [`movie_recommender`](movie_recommender/SKILL.md) | Recommend 5–8 films from a user-supplied taste profile, verifying titles and directors via Wikipedia before naming them. | — |
| [`newsletter`](newsletter/SKILL.md) | Fetch RSS / Atom feeds and produce a digest — single-feed or keyword-filtered across many. Read/digest only (no cron + email). | — |
| [`paper_scout`](paper_scout/SKILL.md) | Discover and summarise research papers via arXiv + Semantic Scholar, with citation counts and references. | — |
| [`recipe_composer`](recipe_composer/SKILL.md) | Pure skill — suggest 3–5 cookable recipes for tonight from a user-supplied pantry, respecting diet and allergies. No scripts. | — |
| [`stock_alert`](stock_alert/SKILL.md) | Look up crypto + stock prices with 24h change (no alerting loop). Crypto keyless via CoinGecko; stocks via Alpha Vantage. | ALPHA_VANTAGE (stocks only) |
| [`travel_planner`](travel_planner/SKILL.md) | Prescriptive multi-day travel itinerary — Wikipedia → weather → geocode → attractions → web → write. | TAVILY · OPENTRIPMAP |
| [`trip_designer`](trip_designer/SKILL.md) | Goal-shaped travel itinerary — you pick decomposition (by day / region / theme / budget bucket); for off-template briefs and hard constraints. | TAVILY · OPENTRIPMAP |
| [`web_researcher`](web_researcher/SKILL.md) | One-shot web research pass — 2–4 angled searches, optional page fetches, sourced report. For ad-hoc "what's the state of X" questions. | TAVILY |
| [`webpage_summarizer`](webpage_summarizer/SKILL.md) | Fetch any URL and produce a structured summary — title, overview, key topics, notable facts, takeaway. | — |
| [`wiki_dive`](wiki_dive/SKILL.md) | Deep Wikipedia research — full sections, related links, structured synthesis with citations. | — |
| [`youtube_research`](youtube_research/SKILL.md) | Research a topic via YouTube — find videos, fetch transcripts, synthesise with timestamped citations. | TAVILY |

## Importing a skill into a CUGA agent

CUGA discovers `SKILL.md` files under `<cuga_folder>/skills/**/`, where
`cuga_folder` is the same folder you pass to `CugaAgent(cuga_folder=…)`
(or the `CUGA_FOLDER` env var). Two install targets:

| Where | Effect |
| --- | --- |
| `<project>/.cuga/skills/<name>/` | Project-local — only this project sees it |
| `~/.config/agents/skills/<name>/` | Global — every CUGA agent on the machine sees it |

Then enable skills via:

```bash
export DYNACONF_SKILLS__ENABLED=true
```

**Use `cp -R`, not symlinks.** CUGA's loader uses `Path.rglob('SKILL.md')`,
which doesn't follow top-level symlinked directories on Python ≤ 3.12 —
symlinked installs fail silently.

The companion [`cuga-skills-ui/`](../cuga-skills-ui/) wires this up
automatically: list every skill in `cuga-skills/`, click Import, ask a
question.

## Authoring a new skill

1. Copy [`_template/`](_template/) to `cuga-skills/<your_skill>/` and rename
   `SKILL.template.md` → `SKILL.md` and `scripts/hike_tools.template.py` →
   `scripts/<your-script>.py`.
2. Fill in the SKILL.md frontmatter (`name`, `description`, optional
   `requirements: [...]`) and body.
3. Replace the placeholder helpers in `scripts/<your-script>.py` with real
   stdlib (or pip-declared) Python. Keep it pure — no langchain, no
   framework imports. Just functions + a CLI dispatcher that prints JSON.
4. Restart the UI (or your host) so the registry rescans.

See [hiking_research](hiking_research/) as a worked example, and
[CONVERSION_PLAYBOOK.md](CONVERSION_PLAYBOOK.md) for full mechanics.

### Two hosts, one skill

| Host | What it does |
| --- | --- |
| `cuga-skills-ui` (in-process, no Docker) | Provides a host-side `run_command` that subprocesses on your laptop. SKILL.md unchanged. |
| `cuga start demo_skills` (with OpenSandbox) | Uploads the skill folder into the Docker sandbox; the sandbox's built-in `run_command` runs the script. SKILL.md unchanged. |

The published skill artifact is identical in both cases. That's the point.
