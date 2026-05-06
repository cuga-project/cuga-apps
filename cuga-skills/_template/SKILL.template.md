---
name: TODO_skill_name
description: TODO one-line, trigger-rich description. Mention the user-facing intent verbs ("Discover and compare hikes near a location"), not the implementation ("Wraps OpenStreetMap"). The agent reads this to decide whether to load this skill.
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

| Tool | Purpose |
| --- | --- |
| `tool_a(arg)` | TODO one-line purpose. |
| `tool_b(arg1, arg2=default)` | TODO one-line purpose. |

If your skill ships a `tools.py`, both helpers can be invoked **two ways**
depending on the host:

**Native invocation (LangChain tool):** the host pre-loaded `tools.py`;
helpers are callable as native tools — e.g. `tool_a(arg="...")`.

**Sandbox invocation (CLI via run_command):** the same logic via subprocess:

```python
import json
out = await run_command(
    "python /tmp/cuga_workspace/skills/TODO_skill_name/tools.py tool_a 'value'"
)
result = json.loads(out)
```

Both paths return the same JSON shape — pick whichever your host has.

If your skill is **pure** (no `tools.py`), delete this whole section.

## Workflow

TODO numbered steps the agent should follow. Reference tools by name.

1. ...
2. ...
3. ...

## Tone & failure modes

- TODO be concise / verbose / formal — pick one.
- TODO what to say when a tool returns empty.
- TODO what to NEVER fabricate.

## Output format

TODO show an example of the exact rendered output the agent should produce.
A code block with `...` placeholders works well — it gives the agent a
schema to fill in.

```
TODO example output schema
```
