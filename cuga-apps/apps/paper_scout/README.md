# Paper Scout

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

arXiv + Semantic Scholar paper discovery and references.

**MCP servers consumed:**
- **mcp-knowledge** — `search_arxiv` · `get_arxiv_paper` · `search_semantic_scholar` · `get_paper_references`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Academic paper research agent powered by arXiv and Semantic Scholar. Research any topic, get structured syntheses with citations, or paste an arXiv ID for an instant structured summary.

**No API keys required.** Both arXiv and Semantic Scholar offer free public APIs.

## Port

`28808` — http://localhost:28808

## Run

```bash
cd apps/paper_scout
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

## Data Sources

| Source | Coverage | What it adds |
|---|---|---|
| **arXiv** | CS, ML, physics, math, econ, q-bio | Latest preprints, PDFs |
| **Semantic Scholar** | All disciplines | Citation counts, cross-domain search |

The agent searches both sources and deduplicates results.

## Example Prompts

1. **Topic research**
   - `LoRA and parameter-efficient fine-tuning methods`
   - `Mixture of Experts in large language models`
   - `Retrieval-Augmented Generation for knowledge-intensive NLP`
   - `Diffusion models for protein structure generation`
   - `Mechanistic interpretability of transformer attention heads`

2. **Direct arXiv lookup**
   - `https://arxiv.org/abs/2305.11206`
   - `2310.01445` ← paste the ID directly
   - `Summarise arxiv 1706.03762` (Attention Is All You Need)

3. **Follow-up questions**
   - `What papers does this build on?`
   - `Find me the most cited papers on this topic`
   - `Any recent work (last 6 months) on this?`
   - `What are the open problems in this area?`

## Tools

| Tool | Source | What it does |
|---|---|---|
| `search_arxiv` | arXiv API | Keyword search, category filter, sorted by date |
| `get_arxiv_paper` | arXiv API | Fetch specific paper by ID |
| `search_semantic_scholar` | Semantic Scholar API | Broader search with citation counts |
| `get_paper_references` | Semantic Scholar API | Fetch what a paper cites |

## Architecture

```
User query
    │  POST /ask
    ▼
CugaAgent
    ├─ search_arxiv(query)              → up to 6 recent preprints
    ├─ search_semantic_scholar(query)   → up to 6 papers with citation counts
    └─ (optional) get_paper_references  → reference list for a specific paper
    ▼
Synthesised report with:
  - Papers grouped by theme
  - Citation format: [Title](url) by Author et al. (year) — N citations
  - Key papers to read first
  - Suggested follow-up queries
```
