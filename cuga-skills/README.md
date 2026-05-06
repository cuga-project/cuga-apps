# cuga-skills

A library of reusable [agent skills](https://github.com/anthropics/skills) for
CUGA. Each subdirectory is a self-contained skill: a `SKILL.md` (frontmatter +
markdown playbook) plus any companion scripts/templates.

## Layout

```
cuga-skills/
├── README.md
├── CONVERSION_PLAYBOOK.md     # how to convert cuga-apps → portable skills
├── _template/                 # skeleton SKILL.md + tools.py for new skills
└── <skill_name>/
    ├── SKILL.md               # required — frontmatter + body
    └── tools.py               # optional — dual-host: importable + CLI
```

- **Running it** → [QUICKSTART.md](QUICKSTART.md) — two terminals, watsonx,
  bare uvicorn (skips the digital_sales preset). Read this first.
- **Authoring new skills** → [CONVERSION_PLAYBOOK.md](CONVERSION_PLAYBOOK.md)
  — classification rules, dual-host format, per-app recipe, quality
  checklist, test protocol.

Discovered skills:

| Skill | Description |
| --- | --- |
| [`hiking_research`](hiking_research/SKILL.md) | Discover and compare hikes near a location using OpenStreetMap + web reviews |

## Importing a skill into a CUGA agent

CUGA discovers `SKILL.md` files under `<cuga_folder>/skills/**/`, where
`cuga_folder` is the same folder you pass to `CugaAgent(cuga_folder=…)` (or the
`CUGA_FOLDER` env var). To use a skill from this directory, copy or symlink its
folder into `<your_cuga_folder>/skills/<skill_name>/`, then enable skills via:

```bash
export DYNACONF_SKILLS__ENABLED=true
```

The companion [`cuga-skills-ui/`](../cuga-skills-ui/) demo wires this up
automatically: it lists every skill in `cuga-skills/`, lets you import one, and
asks the agent a question against that skill.

## Authoring a new skill

1. Create `cuga-skills/<your_skill>/SKILL.md` with frontmatter:
   ```markdown
   ---
   name: your_skill
   description: One-line description (shown in the available-skills prompt block).
   ---

   # Your skill body — when to use, workflow, quick references, output format.
   ```
2. **Optional but powerful** — add `cuga-skills/<your_skill>/tools.py`
   exporting a `TOOLS = [...]` list of LangChain `@tool` functions. When the
   skill is imported through `cuga-skills-ui`, these are passed to
   `CugaAgent(tools=...)` so the agent can call them directly with no
   sandbox required (see [`hiking_research/tools.py`](hiking_research/tools.py)
   for an example).
3. Restart the UI (or your host app) so the registry rescans.

### Two execution paths a skill can support

| Host | What runs |
| --- | --- |
| `cuga-skills-ui` (in-process, no sandbox) | `tools.py` → native LangChain tools. SKILL.md is the playbook. |
| `cuga start demo_skills` (with OpenSandbox) | Skill folder is uploaded into the sandbox; SKILL.md tells the agent to `run_command` against scripts. |

A well-designed skill works in both — `tools.py` exposes pure helpers, and
`SKILL.md` references them by name without prescribing which host runs them.
