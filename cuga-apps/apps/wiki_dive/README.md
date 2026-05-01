# Wiki Dive

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Deep Wikipedia research: search, lead, sections, related articles.

**MCP servers consumed:**
- **mcp-knowledge** — `search_wikipedia` · `get_article_summary` · `get_article_sections` · `get_related_articles`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Deep Wikipedia research agent. Goes beyond a keyword search — reads articles section by section, follows related links, and synthesises a structured report with citations and cross-article connections.

**No API keys required.** Uses Wikipedia's free public REST and action APIs.

## Port

`28809` — http://localhost:28809

## Run

```bash
cd apps/wiki_dive
python main.py
# or with a specific provider
python main.py --provider anthropic --model claude-sonnet-4-6
python main.py --provider openai --model gpt-4o
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Yes | Model name for the chosen provider |
| `AGENT_SETTING_CONFIG` | Yes | Path to the agent settings TOML file |
| `ANTHROPIC_API_KEY` | When using Anthropic | Anthropic API key |
| `OPENAI_API_KEY` | When using OpenAI | OpenAI API key |
| `RITS_API_KEY` | When using RITS | RITS API key |

No app-specific API keys required.

## What makes this different from a Wikipedia search

| Wikipedia search | Wiki Dive |
|---|---|
| Returns page titles and snippets | Reads full article sections |
| One article at a time | Follows related links to pull connected concepts |
| Raw article text | Synthesised report with cross-article citations |
| You read and connect the dots | Agent builds the mental model for you |

## Example Prompts

1. **Scientific concepts**
   - `How does transformer attention work?`
   - `Quantum entanglement — explain from first principles`
   - `CRISPR gene editing and its applications`
   - `The history and science of plate tectonics`

2. **Historical events and figures**
   - `The French Revolution — causes, events, and legacy`
   - `The Byzantine Empire — rise and fall`
   - `Alan Turing's contributions to computing`

3. **Philosophy and theory**
   - `The philosophy of consciousness and the hard problem`
   - `Game theory and Nash equilibrium`
   - `What is Bayesian inference?`

4. **Current technology**
   - `How do large language models work?`
   - `The history of the internet`
   - `How does the immune system respond to viruses?`

## Tools

| Tool | What it does |
|---|---|
| `search_wikipedia` | Find relevant articles by keyword |
| `get_article_summary` | Read the lead/introduction of an article |
| `get_article_sections` | Read the full article section by section |
| `get_related_articles` | Discover related Wikipedia pages |

## Architecture

```
User query
    │  POST /ask
    ▼
CugaAgent
    ├─ search_wikipedia(query)         → find most relevant article(s)
    ├─ get_article_summary(title)      → quick relevance check
    ├─ get_article_sections(title)     → deep read: all sections
    ├─ get_related_articles(title)     → discover connected concepts
    └─ get_article_summary(related)    → pull 2-3 related articles
    ▼
Synthesised report:
  - Overview (2-3 paragraphs)
  - Key concepts with citations
  - History / development
  - Current state / applications
  - Related topics to explore
```
