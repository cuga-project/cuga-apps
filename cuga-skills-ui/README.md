# cuga-skills-ui

A super-simple browser UX for trying CUGA agent skills from
[`../cuga-skills/`](../cuga-skills/) — **standalone**, in-process, no
separate CUGA server, no Docker, no OpenSandbox.

```
   ┌──────────────┐    Import     ┌─────────────────────────────────┐
   │ cuga-skills/ │ ────────────► │ ./.cuga/skills/<name>/          │ ◄── cuga's loader
   └──────────────┘    (cp -R)    │ /tmp/cuga_workspace/skills/<n>/ │ ◄── run_command paths
                                  └────────────┬────────────────────┘
                                               │
                                               ▼
                                  ┌──────────────────────────────────┐
                                  │ CugaAgent(cuga_folder=.cuga,     │
                                  │          tools=[run_command])    │
                                  └──────────┬───────────────────────┘
                                             │
                                             ▼  agent: load_skill → run_command(...)
                                       /ask {question}
```

The host emulates an OpenSandbox sandbox in-process: provides its own
`run_command` that subprocesses on the local machine, with `cwd=/tmp/cuga_workspace`
so SKILL.md paths line up with what `cuga start demo_skills` would see.
**Same skill folder, same answer in both hosts.** The only differences
are speed (no Docker = faster) and isolation (none — don't expose to
untrusted skills or networks).

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
2. **Import** copies a skill folder into both:
   - `./.cuga/skills/<name>/` — so cuga's `discover_skills()` registers it.
   - `/tmp/cuga_workspace/skills/<name>/` — so SKILL.md's `run_command`
     paths (`/tmp/cuga_workspace/skills/<name>/scripts/...`) resolve.
3. **Ask** invokes `agent.invoke(question)`. The agent sees `load_skill`
   and `run_command` in its tool list, calls `load_skill("<name>")` to
   read the playbook, then `run_command("python /tmp/cuga_workspace/skills/<name>/scripts/<file>.py …")`
   to actually execute.

The UI lazy-rebuilds the agent whenever the imported set changes, so adding
or removing a skill takes effect on the next Ask.

## Skill execution model

This app sets, before importing `cuga`:

```
DYNACONF_SKILLS__ENABLED=true
DYNACONF_ADVANCED_FEATURES__OPENSANDBOX_SANDBOX=false
DYNACONF_ADVANCED_FEATURES__ENABLE_SHELL_TOOL=false
```

OpenSandbox is off (no Docker). The agent's `run_command` is a host-side
@tool wrapper around `subprocess.run(shlex.split(cmd), cwd=/tmp/cuga_workspace)`.
The skill folder you imported lives at `/tmp/cuga_workspace/skills/<name>/`,
identical to where OpenSandbox would put it inside its container — so the
SKILL.md instructions work without modification.

### Reusing a skill globally

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

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/skills` | `{available, skills_root, runtime_cuga_folder, sandbox_dir}`; each item has `installed: bool` and `has_scripts: bool`. |
| `POST` | `/import` `{name}` | Copy `<name>` into both install targets. |
| `POST` | `/uninstall` `{name}` | Remove from both targets. |
| `POST` | `/ask` `{question}` | `await agent.invoke(question)` and return `{answer}`. |
| `GET` | `/` | The HTML page. |

## Layout

```
cuga-skills-ui/
├── README.md
├── requirements.txt
├── main.py                    # FastAPI server + embedded HTML page
├── .cuga/                     # runtime — created on first import (gitignored)
│   └── skills/
│       └── <name>/            # imported skill copies (cuga loader scans here)
└── /tmp/cuga_workspace/       # NOT inside this dir — global; matches sandbox layout
    └── skills/
        └── <name>/            # ← run_command's cwd resolves paths here
```

## Adding more skills

Drop `<name>/SKILL.md` (+ optional `<name>/scripts/`) under
`../cuga-skills/` and refresh the page.
