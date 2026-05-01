# Smart Todo

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Conversational todo list; SQLite store + email reminders.

**MCP servers consumed:** _none — all tools stay inline (see below)._

**Inline `@tool` defs (kept local because they touch app-specific state):** `save_todo` · `list_todos` · `mark_done`

<!-- END: MCP usage -->

A conversational todo manager with natural language input, due-date reminders, and email delivery. Tell the agent what you need to do and it handles the rest.

**Port:** 28800

## Features

- **Natural language** — add todos by chatting, no rigid form needed
- **Due-date tracking** — set deadlines like "tomorrow" or "Friday 3pm"
- **Email reminders** — background watcher fires an email when items come due
- **Persistent storage** — todos stored in `todos.db` (SQLite, survives restarts)
- **Todo board** — tabbed view: Todos / Reminders / Notes / Done
- **Browser UI** — chat panel + visual board in one page

## Quick Start

```bash
pip install -r requirements.txt
python main.py
# open http://127.0.0.1:28800
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | — | `rits` \| `anthropic` \| `openai` \| `ollama` |
| `LLM_MODEL` | — | Model override |
| `SMTP_HOST` | — | e.g. `smtp.gmail.com` |
| `SMTP_USERNAME` | — | Your email address |
| `SMTP_PASSWORD` | — | App password |
| `ALERT_TO` | — | Reminder recipient email |

## Usage

1. Start the server and open the browser UI
2. Chat with the agent: *"Remind me to submit the report by Friday"*
3. The agent saves the todo with a due date
4. At due time, the reminder watcher sends you an email
5. View all todos on the board to the right

## Example Phrases

- "Add a todo: review Q1 budget by Monday"
- "What's due this week?"
- "Mark the report submission as done"
- "Show me all open items"
- "Add a note: check with Alice about the project timeline"
