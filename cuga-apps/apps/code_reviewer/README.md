# Code Reviewer

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Stdlib-only code analysis: syntax, metrics, language detection.

**MCP servers consumed:**
- **mcp-code** — `check_python_syntax` · `extract_code_metrics` · `detect_language`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

AI-powered code review tool built with Cuga. Paste code or upload a file and get structured feedback covering bugs, security, performance, style, and architecture insights.

## Port

`28807` — `http://127.0.0.1:28807`

## Run

```bash
python main.py                               # auto-detect LLM from env vars
python main.py --provider anthropic          # use Anthropic Claude
python main.py --provider openai             # use OpenAI
python main.py --provider openai --model gpt-4.1
python main.py --port 8080                   # custom port
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes (or pass `--provider`) | `anthropic` \| `openai` \| `rits` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | No | Model name override (e.g. `claude-sonnet-4-6`, `gpt-4.1`) |
| `ANTHROPIC_API_KEY` | If using Anthropic | Anthropic API key |
| `OPENAI_API_KEY` | If using OpenAI | OpenAI API key |

## Features

- **Paste or upload** — textarea for quick pastes, file upload for `.py`, `.js`, `.ts`, `.java`, `.go`, `.rs`, `.cpp`, `.sql`, `.sh`, and more
- **Focus modes** — Full Review, Security, Performance, Style, Bugs, Architecture, Testability
- **Language auto-detection** — heuristic detection + manual override
- **Syntax check** — AST-level Python syntax validation before review
- **Code metrics** — LOC, complexity estimate, top-level definitions
- **Follow-up questions** — ask the agent anything about the loaded code
- **Review history** — collapsible log of all reviews this session
- **Copy button** — one-click copy of any review

## Example prompts to try

1. Paste a Python function and click **Review Code** with "Bugs" focus to find logic errors
2. Upload a JavaScript file, select "Security" focus, and ask "Is there any XSS risk?"
3. Paste a SQL query and ask "How could I optimise this query for a table with 10M rows?"
4. Load a Go file and click "Architecture" to get design pattern analysis
5. Paste any code and use the follow-up box: "How would you refactor this using the strategy pattern?"
