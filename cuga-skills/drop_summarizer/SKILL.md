---
name: drop_summarizer
description: Extract and summarise the contents of a local document the user supplies by file path (.txt, .md, .pdf, .docx, .pptx, .xlsx, .csv). Use when the user uploads, drops, or names a path to a file and wants a TL;DR with key points and action items.
requirements:
  - pypdf>=4.0
  - python-docx>=1.1
examples:
  - "Summarize /tmp/notes.pdf"
  - "TL;DR of ./meeting-2026-04.docx"
  - "What's in this file: ~/Downloads/report.pptx"
  - "Action items from /tmp/standup-notes.md"
---

# Drop Summarizer

You produce concise, structured summaries of a single document the
user supplies by **local file path**. A companion script —
`scripts/extract_tools.py` — exposes one subcommand: `extract_text
<file_path>` which returns the document's plain-text content.

## When to use this skill

Trigger on any request that involves:

- "Summarize / TL;DR / brief / digest &lt;file_path&gt;"
- "Action items / decisions / key points from &lt;file&gt;"
- "What's in this file: &lt;path&gt;"
- A bare local file path with no other ask — assume a summary is wanted

The user must give a **path** (absolute or relative). If they paste
content inline, summarise it directly without calling the tool.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `extract_text <file_path> [max_chars=50000]` | Read a local file and return plain text. Supported types: `.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.pptx`, `.xlsx`. | `{file_path, file_name, ext, content, char_count, truncated}` or `{error}` |

Image files (PNG/JPG/etc.) are **not supported** in this version —
return a clear error pointing the user at a vision-capable host.

### Example invocation

```
python scripts/extract_tools.py extract_text /tmp/notes.pdf
python scripts/extract_tools.py extract_text ~/Downloads/report.docx 30000
```

## Workflow

1. `extract_text(file_path)` to get the plain-text content. If it
   returns `{error}`, surface it plainly and stop — don't fabricate.
2. If `truncated: true`, note that the summary is from the first ~N
   characters and offer to re-run on a different range if needed.
3. Produce the summary in the format below.

## Summary format

```
**<TL;DR — one sentence>**

**Key points**
- <point 1 — fact, decision, or key claim>
- <point 2>
- <point 3>
- ...
(3-5 bullets)

**Action items** (if present)
- <action> — <owner if mentioned> — <deadline if mentioned>
- ...

**Notable details** (if relevant)
- <number, date, name, or quote worth surfacing>
- ...
```

Keep the whole summary under ~15 lines. If the document is empty or
near-empty, say so and ask the user for a different path.

## Tone & failure modes

- Lead with one TL;DR sentence — no "this document is about" filler.
- Action items only when they're actually in the text — don't invent.
- For code files, summarise purpose + main components.
- For specs / contracts, surface the most consequential clauses.
- For meeting notes, prioritise decisions and owners.
- **Never invent content** — if the extraction returned little, say
  the document was sparse rather than padding.
- For unsupported types (image, video, audio), say so plainly and
  suggest a vision-capable host or transcription tool.
- If your host has no way to execute the script, say so plainly. Do
  not invent file contents.
