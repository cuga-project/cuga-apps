---
name: TODO_skill_name
description: TODO one-line, trigger-rich description. Mention the user-facing intent verbs ("Discover and compare hikes near a location"), not the implementation ("Wraps OpenStreetMap"). The agent reads this to decide whether to load this skill.
requirements: []
---

# TODO_skill_name Assistant

TODO one-paragraph framing of what this skill does for the user, and which
helpers (if any) are available.

## When to use this skill

TODO bulleted list of trigger phrases. Be specific — these are what the
agent's routing depends on.

- "Find / look up / search for X near Y"
- "Compare / score / evaluate Z"
- ...

## Tools provided

If your skill ships a `scripts/` directory, the agent runs the script as
a subprocess (using whatever shell-execution primitive its host provides)
and parses JSON from stdout. Reference the script by its relative path
inside this skill folder — the host's harness resolves where the folder
is mounted. Don't hardcode absolute paths or host-specific tool names.

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `tool_a <arg>` | TODO one-line purpose. | `{...}` |
| `tool_b <arg1> [arg2]` | TODO one-line purpose. | List of `{...}` |

### Example invocation

The exact subprocess call depends on the host. Schematically:

```
python scripts/<filename>.py tool_a 'value'
# → {...}
```

If your skill is **pure** (no scripts), delete this whole section.

## Workflow

TODO numbered steps the agent should follow. Reference subcommands by name.

1. ...
2. ...
3. ...

## Tone & failure modes

- TODO be concise / verbose / formal — pick one.
- TODO what to say when a tool returns empty.
- TODO what to NEVER fabricate.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not guess.

## Output format

TODO show an example of the exact rendered output the agent should produce.
A code block with `...` placeholders works well — it gives the agent a
schema to fill in.

```
TODO example output schema
```
