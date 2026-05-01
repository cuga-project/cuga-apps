# Voice Journal

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Voice/text journal — transcribe, save, search by date.

**MCP servers consumed:**
- **mcp-local** — `transcribe_audio`

**Inline `@tool` defs (kept local because they touch app-specific state):** `save_journal_entry` · `list_entries` · `list_dates`

<!-- END: MCP usage -->

A personal journal that accepts audio recordings and text entries. Transcribes audio with OpenAI Whisper, stores entries in SQLite, and sends a weekly digest to your inbox.

**Port:** 28799

## Features

- **Audio transcription** — drop `.m4a`, `.mp3`, `.wav` files; transcribed via OpenAI Whisper API (or local Whisper as fallback)
- **Text entries** — quick-write textarea or chat with the agent
- **Inbox watcher** — monitors `./inbox` for new audio and text files automatically
- **Weekly digest** — configurable email digest of recent entries
- **Persistent storage** — entries in `journal.db` + Markdown files under `./entries/`
- **Timeline UI** — scrollable entry history on the right panel

## Quick Start

```bash
pip install -r requirements.txt
# For local transcription fallback:
# pip install openai-whisper
python main.py
# open http://127.0.0.1:28799
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | — | `rits` \| `anthropic` \| `openai` \| `ollama` |
| `LLM_MODEL` | — | Model override |
| `OPENAI_API_KEY` | — | Required for Whisper API transcription |
| `SMTP_HOST` | — | e.g. `smtp.gmail.com` |
| `SMTP_USERNAME` | — | Your email address |
| `SMTP_PASSWORD` | — | App password |
| `DIGEST_TO` | — | Digest recipient email |

## Usage

1. Start the server and open the browser UI
2. Upload audio or type an entry using the quick-write panel
3. Audio files are transcribed and saved as journal entries automatically
4. Configure digest schedule (daily / weekly) and email in the settings panel
5. Chat with the agent to reflect on your entries

## Example Questions

- "What did I write about last week?"
- "Summarize my entries from this month"
- "What themes keep coming up in my journal?"
- "Show me everything I recorded on Monday"
