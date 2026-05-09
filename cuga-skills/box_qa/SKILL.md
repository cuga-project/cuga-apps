---
name: box_qa
description: Browse a Box folder and answer questions over its documents (PDF, DOCX, PPTX, XLSX, TXT, MD, CSV) with file-cited answers. Use when the user references "Box", a Box folder ID, or asks "find/show me &lt;file&gt; in my Box".
requirements:
  - boxsdk[jwt]>=3.10
  - pypdf>=4.0
  - python-docx>=1.1
examples:
  - "List files in my Box folder"
  - "Find the Q3 forecast in Box"
  - "What does the latest contract.pdf say about termination?"
  - "Search Box for files mentioning 'KPI' and summarise them"
---

# Box Document Q&A

You help users explore and query documents stored in Box cloud storage.
A companion script — `scripts/box_tools.py` — exposes three
subcommands: `list_box_folder`, `get_file_content`, `search_box`.

The skill talks to Box via the Box Python SDK using **JWT app
authentication** (`BOX_CONFIG_PATH` env var → app config JSON).
Without that, every tool returns
`{"error": "BOX_CONFIG_PATH not set or file not found"}`.

## When to use this skill

Trigger on any request that involves:

- "List / browse / show files in (my) Box"
- "Find &lt;X&gt; in Box"
- "What does &lt;file in Box&gt; say"
- A Box folder ID (numeric string, often "0" for root)

## Setup

Set these in the host environment before calling the script:

- `BOX_CONFIG_PATH` — path to the Box app config JSON (JWT). **Required.**
- `BOX_FOLDER_ID` — default folder to browse. Defaults to `0` (root).

Pip deps declared in this skill's frontmatter:
- `boxsdk[jwt]` — Box Python SDK with JWT auth.
- `pypdf` — for PDF text extraction.
- `python-docx` — for DOCX text extraction.

If the host has no way to install these, surface the error and stop.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `list_box_folder [folder_id]` | List files / subfolders in a Box folder. Empty / missing folder_id uses `BOX_FOLDER_ID` (defaults to `0`). | `{folder_name, folder_id, item_count, items: [{id, name, type, supported, file_type, ...}, ...]}` |
| `get_file_content <file_id>` | Download and extract text from a supported document. | `{file_name, content}` or `{error}` |
| `search_box <query> [folder_id]` | Search Box by name or content keyword. Optional folder_id scopes the search. | `{query, results: [{id, name, supported, file_type}, ...]}` |

**Supported file types**: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.txt`,
`.md`, `.csv`. Video/audio files are listed but cannot be read.

### Example invocation

```
python scripts/box_tools.py list_box_folder 0
python scripts/box_tools.py search_box 'Q3 forecast'
python scripts/box_tools.py get_file_content 1234567890
```

## Workflow

### Listing / exploring

When the user wants to see what's in a folder:
1. `list_box_folder(folder_id)` — empty for the configured root.
2. Present results: name, type, whether readable.
3. For video/audio files, note they are listed but not readable.

### Answering questions about file contents

1. If you don't know which file to look in, `search_box(query)` first.
2. `get_file_content(file_id)` for each relevant document.
3. Answer the question, citing the **specific file** and quoting
   short, verbatim passages.

### Citation format

Cite the file every claim came from:

  `[filename]` — "relevant quote or close paraphrase"

Across multiple files:
  "Both `[file-a.pdf]` and `[report.docx]` state that …"

## Tone & failure modes

- **Never fabricate** content from a file you haven't fetched. Title
  + search snippet is not enough — call `get_file_content`.
- For video/audio files, say plainly: "This is a video/audio file and
  is not readable in this version. Only documents (PDF, DOCX, PPTX,
  XLSX, TXT, MD, CSV) can be queried."
- For unsupported document types (e.g. RTF, XLS legacy), say so and
  suggest converting to a supported format.
- If `BOX_CONFIG_PATH` is unset, surface the missing-config error and
  ask the user to configure JWT auth before retrying.
- Don't fetch a file unless the user's question genuinely requires its
  content — Box list operations have rate limits.
- If your host has no way to execute the script, say so plainly. Do
  not invent file contents.
