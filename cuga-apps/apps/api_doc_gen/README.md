# api_doc_gen — API Documentation Generator

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Inspect uploaded OpenAPI specs; per-process loaded spec.

**MCP servers consumed:** _none — all tools stay inline (see below)._

**Inline `@tool` defs (kept local because they touch app-specific state):** `list_endpoints` · `get_endpoint_details` · `get_schema`

<!-- END: MCP usage -->

Generate human-readable API docs from OpenAPI/Swagger specs. Upload a spec, pick a built-in sample, or point to a URL — then ask the agent to write the docs.

**Port:** 28811

## Run

```bash
cd apps/api_doc_gen
python main.py --provider anthropic
python main.py --provider openai
python main.py --port 28811 --provider rits --model llama-3-3-70b-instruct
```

Then open: http://127.0.0.1:28811

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Always | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Always | Model name, e.g. `claude-sonnet-4-6`, `gpt-4o`, `llama-3-3-70b-instruct` |
| `AGENT_SETTING_CONFIG` | Always | Path to Cuga settings TOML |
| `ANTHROPIC_API_KEY` | When using Anthropic | — |
| `OPENAI_API_KEY` | When using OpenAI | — |
| `RITS_API_KEY` | When using RITS | — |

## Built-in sample specs

| Sample | Endpoints | Description |
|---|---|---|
| **Petstore API** | 9 | Classic CRUD — pets, orders, users |
| **GitHub Issues API** | 8 | Issues, comments, labels on repos |
| **Stripe Payments API** | 9 | Customers, charges, subscriptions, refunds |
| **Slack Messaging API** | 6 | Post messages, channels, reactions, users |
| **OpenWeather API** | 4 | Current weather, forecast, air quality |

## Example prompts to try

- `Document all endpoints` — full docs for every endpoint in the loaded spec
- `Show me the authentication details and how to get started` — auth section with setup instructions
- `Generate a quick-start guide for a new developer` — intro + first API call walkthrough
- `Document only the POST endpoints with example request bodies` — filtered docs
- `List all endpoints with a one-line description of each` — endpoint overview table
- `Add more realistic example values to the responses` — iterative refinement
- `Generate a Postman collection structure for these endpoints` — format change

## Input formats

- **OpenAPI 3.x** JSON or YAML
- **Swagger 2.x** JSON or YAML
- Upload file, paste a URL, or use a built-in sample
