# Recipe Composer

Tell the agent what's in your pantry. It tracks ingredients, respects diet
and allergies, looks up rough macros, and proposes 3–5 cookable recipes for
tonight — each with a "use this / pick that up" breakdown and optional
step-by-step instructions.

**Port:** 28820 → http://localhost:28820
**Tools:** all inline `@tool` defs — no MCP, no external APIs, no API keys.

## How it works

1. The user mentions ingredients in chat. The agent calls `add_to_pantry`
   for each one.
2. The agent listens for diet (`set_diet`) and allergies (`add_allergy`)
   as they come up.
3. When asked for ideas, the agent calls `list_pantry`, brainstorms 3–5
   dishes, validates each with `check_diet_compatibility`, optionally
   estimates macros with `estimate_macros`, and persists the result via
   `save_recipes`.
4. The right panel auto-refreshes every 10 s and shows pantry, diet,
   allergies, and the latest recipe cards.

## Run

```bash
pip install -r requirements.txt
pip install -e /path/to/cuga-agent     # if not already installed

export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...

python main.py --port 28820
# open http://127.0.0.1:28820
```

## Environment variables

| Var | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | yes | Model name |
| `AGENT_SETTING_CONFIG` | yes (defaulted) | Path to CUGA settings TOML; defaulted per-provider in `make_agent()`. |

No tool-side API keys — the macro and substitution tables are baked in.

## Example prompts

- "I have chicken breast, rice, broccoli, and soy sauce."
- "Add eggs, spinach, and a tomato to my pantry."
- "I'm vegetarian and allergic to peanut butter."
- "What can I cook tonight in under 25 minutes?"
- "Roughly how many calories in a 200 g portion of pasta?"
- "What can I substitute for butter in a sauté?"

## Tools (all inline)

| Tool | Purpose |
|---|---|
| `add_to_pantry` | Add an ingredient to the session pantry. |
| `remove_from_pantry` | Drop an ingredient. |
| `list_pantry` | Read pantry + diet + allergies for this session. |
| `set_diet` | Save a dietary preference (vegetarian, vegan, …, omnivore to clear). |
| `add_allergy` | Mark an ingredient as off-limits. |
| `estimate_macros` | Static lookup of rough macros per ingredient + portion. |
| `suggest_substitution` | Pantry-friendly swaps from a small mapping table. |
| `check_diet_compatibility` | Filter a candidate ingredient list by diet + allergies. |
| `save_recipes` | Persist structured recipe cards for the right panel. |

## Integration into cuga-apps

This app is already in the right shape for the in-repo layout:

1. The folder lives at `apps/recipe_composer/` — no move needed.
2. Add the port `recipe_composer: 28820` to `apps/_ports.py` (`APP_PORTS`).
3. Register it in `apps/launch.py` (`PROCS` list).
4. Add a tile entry in `ui/src/data/usecases.ts`.
5. Add it to `start.sh` and `docker-compose.yml`.

All inline tools follow the cuga MCP envelope (`{ok, data}` / `{ok: false,
error, code}`), so any of them — e.g. `estimate_macros`, `suggest_substitution`
— could be promoted to a new MCP server (`mcp-nutrition`?) without callsite
changes if they end up reused by other apps.
