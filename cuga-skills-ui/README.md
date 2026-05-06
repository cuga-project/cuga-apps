# cuga-skills-ui

A super-simple browser UX for trying CUGA agent skills from
[`../cuga-skills/`](../cuga-skills/) — **standalone**, in-process, no separate
CUGA server, no Docker, no OpenSandbox.

```
   ┌──────────────┐    Import     ┌──────────────────────────┐
   │ cuga-skills/ │ ────────────► │ runtime .cuga/skills/    │
   └──────────────┘               └──────────┬───────────────┘
                                             │ scanned by
                                             ▼
                                  ┌──────────────────────────┐
                                  │ CugaAgent(cuga_folder=…) │ ◄── in this same process
                                  └──────────┬───────────────┘
                                             │
                                             ▼
                                       /ask {question}
```

## Run

```bash
# 1. activate a venv where cuga is installed (or install it now)
pip install -r requirements.txt
pip install -e /path/to/cuga-agent-skills-branch    # exposes `from cuga import CugaAgent`

# 2. set an LLM key (any one of these)
export ANTHROPIC_API_KEY=...     # or OPENAI_API_KEY, RITS_API_KEY, …

# 3. run
python main.py --provider anthropic
# → http://127.0.0.1:28910
```

Tip: the simplest python to use is the one inside the cuga checkout —
`/path/to/cuga-agent-skills-branch/.venv/bin/python` already has cuga
installed. Activate that venv and just `pip install -r requirements.txt`.

## What it does

1. Scans `../cuga-skills/` for `SKILL.md` files (the local source library).
2. **Import** copies a skill folder into `./.cuga/skills/<name>/`. CUGA's
   `discover_skills` finds it there because we point `CugaAgent` at this
   `.cuga` folder.
3. **Ask** invokes `agent.invoke(question)`. The agent sees the imported
   skills in its prompt's `<available_skills>` block, calls
   `load_skill("<name>")`, and follows the playbook to answer.

The UI lazy-rebuilds the agent whenever the imported set changes, so adding
or removing a skill takes effect on the next Ask.

## Reusing a skill globally

To make any skill in this repo available to *any* CUGA agent on this machine,
copy the folder into the global skills dir:

```bash
mkdir -p ~/.config/agents/skills
cp -R cuga-skills/hiking_research ~/.config/agents/skills/hiking_research
```

> **Use `cp`, not `ln -s`.** CUGA's loader uses `Path.rglob('SKILL.md')`,
> which does **not** follow top-level symlinked skill directories on
> Python ≤ 3.12 — symlinks fail silently. If you want live edits to
> propagate, keep your source in git and re-`cp` on update (or use
> `rsync -a --delete`).

## Skill execution model

This app sets, before importing `cuga`:

```
DYNACONF_SKILLS__ENABLED=true
DYNACONF_ADVANCED_FEATURES__OPENSANDBOX_SANDBOX=false
DYNACONF_ADVANCED_FEATURES__ENABLE_SHELL_TOOL=false
```

The OpenSandbox shell tools (`run_command`, `write_file`, …) are **off**, so
the agent can't shell out to a Docker sandbox. Instead, this UI uses a
lightweight convention so skills can ship their own callable tools:

### `tools.py` convention

If a skill folder contains `tools.py` exporting a `TOOLS` list, the UI
imports it on agent build and passes those tools to `CugaAgent(tools=...)`.
The agent calls them directly — no sandbox required.

```python
# cuga-skills/<skill>/tools.py
from langchain_core.tools import tool

@tool
def my_tool(arg: str) -> dict:
    """Tool description shown to the model."""
    ...

TOOLS = [my_tool]
```

In the UI, a skill that ships `tools.py` is tagged with a blue `+ tools`
badge. The skill's `SKILL.md` body is still loaded via `load_skill` as the
playbook; `tools.py` provides the callable verbs.

This is a host-level convention, not a CUGA-core feature — it's how this
particular UI hands real tools to the agent. If you point at a different
host (e.g. `cuga start demo_skills` with OpenSandbox), the same skill could
instead expose its helpers as `run_command`-able scripts.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/skills` | `{available, skills_root, runtime_cuga_folder}`; each item has `installed: bool`. |
| `POST` | `/import` `{name}` | Copy `<name>` into `./.cuga/skills/<name>/`. |
| `POST` | `/uninstall` `{name}` | Remove from the runtime folder. |
| `POST` | `/ask` `{question}` | `await agent.invoke(question)` and return `{answer}`. |
| `GET` | `/` | The HTML page. |

## Layout

```
cuga-skills-ui/
├── README.md
├── requirements.txt
├── main.py            # FastAPI server + embedded HTML page
└── .cuga/             # runtime — created on first import (gitignored)
    └── skills/
        └── <name>/    # imported skill copies
```

## Adding more skills

Drop `<name>/SKILL.md` under `../cuga-skills/` and refresh the page.
