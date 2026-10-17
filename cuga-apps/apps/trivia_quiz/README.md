# Trivia Quiz Maker

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Look up a topic on Wikipedia and read its article to write a quiz.

**MCP servers consumed:**
- **mcp-knowledge** — `search_wikipedia` · `get_article_summary` · `get_article_sections`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Name any topic and get a 5-question multiple-choice quiz built from its
Wikipedia article, with an answer key that explains each answer.

## Port

**28831**

## Quick start

```bash
pip install -r requirements.txt

export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o
export OPENAI_API_KEY=<your-key>
export AGENT_SETTING_CONFIG=/path/to/settings.toml

python main.py --port 28831
# open http://127.0.0.1:28831
```

## Example prompts

1. `Quiz me on the Roman Empire`
2. `5 questions about volcanoes`
3. `Make a quiz about The Beatles`
4. `Quiz on the solar system, easy level`
5. `Hard quiz about the French Revolution`

## Tools

| Tool | Description |
|---|---|
| `search_wikipedia` | Finds the article for a topic |
| `get_article_summary` | Reads the article summary |
| `get_article_sections` | Reads more detail from the article sections |
