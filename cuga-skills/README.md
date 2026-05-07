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

| Skill | Description |
| --- | --- |
| [`hiking_research`](hiking_research/SKILL.md) | Discover, filter, and evaluate hiking trails near any location using OpenStreetMap |

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
