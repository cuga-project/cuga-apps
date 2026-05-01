# Box Document Q&A

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Natural-language Q&A over Box-stored files (uses mcp-text for extraction).

**MCP servers consumed:**
- **mcp-text** — `extract_text_from_bytes`

**Inline `@tool` defs (kept local because they touch app-specific state):** `list_box_folder` · `get_file_content` · `search_box`

<!-- END: MCP usage -->

Ask questions across documents stored in your Box cloud storage. The agent
lists files, fetches document content, and answers questions with citations.

**Port:** `28810`

## Supported file types

| Type | Extensions |
|------|-----------|
| Documents | PDF, DOCX, PPTX, XLSX, TXT, MD, CSV |
| Not supported (v1) | MP4, MOV, MP3, WAV, and other media |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
pip install -e /Users/anu/Documents/GitHub/cuga-agent-apr10
```

### 2. Box app config

Create a Box app at https://developer.box.com with **Server Authentication (JWT)**.
Download the app config JSON and set:

```bash
export BOX_CONFIG_PATH=/path/to/your-box-app-config.json
export BOX_FOLDER_ID=0   # "0" = root; use a specific folder ID if needed
```

**Important:** Your Box app must be authorized in your Box Admin Console, and the
service account must have access to the folder you want to browse.

### 3. LLM + Cuga config

```bash
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export AGENT_SETTING_CONFIG=/path/to/settings.toml
export ANTHROPIC_API_KEY=<your-key>
```

## Run

```bash
python main.py
python main.py --port 28810
python main.py --provider anthropic
```

Then open: http://127.0.0.1:28810

## Example prompts

- `What files are in my Box folder?`
- `Summarize the document called Q4 Report`
- `Find any files related to contracts and list their key terms`
- `What does the project brief say about timelines?`
- `Compare the two most recent PDFs`

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | Yes | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Yes | Model name for chosen provider |
| `AGENT_SETTING_CONFIG` | Yes | Path to cuga settings TOML |
| `BOX_CONFIG_PATH` | Yes | Path to Box JWT app config JSON |
| `BOX_FOLDER_ID` | No | Box folder ID to browse (default: `"0"` = root) |
