# AI Labs News — CUGA Demo App

A curated, glanceable digest of the latest posts from the major AI labs and
research groups — pulled live from their blog feeds. Ask broadly ("what's new
in AI this week?") or narrowly ("latest from Anthropic and OpenAI on agents"),
and the agent gathers each lab's feed, dedupes, spots cross-lab themes, and
summarizes.

All tools are **inline `@tool` defs**. Live data comes from each lab's public
RSS/Atom feed via `httpx` + `feedparser` — no MCP servers, no API keys.

## Labs covered

OpenAI · Anthropic · Google DeepMind · Google Research · Microsoft Research ·
IBM Research · Meta AI · Hugging Face · Berkeley AI Research (BAIR).

Each lab has one or more **fallback feed URLs** — feeds move and break, so the
tool tries them in order and reports any lab it couldn't reach rather than
inventing news.

## What it does

- **list_labs** — the registry of labs + slugs.
- **set_focus** — restrict to specific labs and/or topic keywords for the session.
- **fetch_lab_news** — recent posts from one lab.
- **fetch_all_news** — merged, newest-first across many labs (the main step).
- **save_digest** — the structured digest (headline + themes + items) the right
  panel renders.

## Run

```bash
cd apps/ai_labs_news
pip install -r requirements.txt    # plus: pip install cuga
python main.py --port 28824
```

Then open <http://127.0.0.1:28824> and try:

- `What's new in AI this week?`
- `Latest from OpenAI, Anthropic, and Google DeepMind`
- `Recent Microsoft Research and IBM Research posts`
- `AI agent news across the labs`

## Endpoints

| Method | Path                   | Purpose                                            |
| ------ | ---------------------- | -------------------------------------------------- |
| GET    | `/`                    | Two-panel UI                                       |
| POST   | `/ask`                 | `{question, thread_id}` → `{answer, thread_id}`    |
| GET    | `/session/{thread_id}` | Session state (focus + saved digest)               |
| GET    | `/health`              | `{"ok": true}`                                     |

## Environment

| Var                    | Required | Notes                                       |
| ---------------------- | -------- | ------------------------------------------- |
| `LLM_PROVIDER`         | yes      | rits \| anthropic \| openai \| watsonx \| … |
| `LLM_MODEL`            | no       | model override                              |
| `AGENT_SETTING_CONFIG` | no       | defaulted in `make_agent`                   |

## Notes

- If a lab's feed URL changes, update its `feeds` list in `_LABS` in `main.py`.
  Adding a new lab is a one-entry change there.
- Feeds vary in how much body text they include; summaries are the feed's own
  description, tag-stripped and truncated — the agent does not embellish them.
