"""CLI helper for the drop_summarizer skill.

Reads a local file (txt/md/csv/pdf/docx/pptx/xlsx) and returns plain text:

    python scripts/extract_tools.py extract_text /tmp/notes.pdf
    python scripts/extract_tools.py extract_text ~/Downloads/report.docx 30000

Pip deps (declared in SKILL.md frontmatter):
  pypdf>=4.0         — PDF text extraction
  python-docx>=1.1   — DOCX text extraction

XLSX and PPTX use stdlib zipfile + xml.etree (Open XML formats).

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

_TEXT = {".txt", ".md", ".csv"}
_SUPPORTED = _TEXT | {".pdf", ".docx", ".pptx", ".xlsx"}
_IMAGE = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"}
_AV = {".mp4", ".mov", ".mkv", ".avi", ".mp3", ".wav", ".m4a", ".aac"}


def _extract_pdf(blob: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "(pypdf not installed — declared in SKILL.md requirements)"
    try:
        reader = PdfReader(io.BytesIO(blob))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception as e:
        return f"(pdf parse error: {type(e).__name__}: {e})"


def _extract_docx(blob: bytes) -> str:
    try:
        from docx import Document
    except ImportError:
        return "(python-docx not installed — declared in SKILL.md requirements)"
    try:
        doc = Document(io.BytesIO(blob))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        return f"(docx parse error: {type(e).__name__}: {e})"


def _extract_xlsx(blob: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            shared: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.findall("x:si", ns):
                    parts = [t.text or "" for t in si.findall(".//x:t", ns)]
                    shared.append("".join(parts))
            sheet_names = sorted(n for n in z.namelist()
                                 if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            chunks: list[str] = []
            for s in sheet_names:
                root = ET.fromstring(z.read(s))
                for row in root.findall(".//x:row", ns):
                    cells = []
                    for c in row.findall("x:c", ns):
                        v = c.find("x:v", ns)
                        if v is None or v.text is None:
                            cells.append("")
                            continue
                        if c.get("t") == "s":
                            try:
                                cells.append(shared[int(v.text)])
                            except (ValueError, IndexError):
                                cells.append(v.text)
                        else:
                            cells.append(v.text)
                    chunks.append("\t".join(cells))
            return "\n".join(chunks).strip() or "(empty xlsx)"
    except Exception as e:
        return f"(xlsx parse error: {type(e).__name__}: {e})"


def _extract_pptx(blob: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            slide_names = sorted(n for n in z.namelist()
                                 if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            chunks: list[str] = []
            for s in slide_names:
                root = ET.fromstring(z.read(s))
                texts = [(t.text or "") for t in root.findall(".//a:t", ns)]
                chunks.append("\n".join(t for t in texts if t.strip()))
            return "\n\n---\n\n".join(c for c in chunks if c).strip() or "(empty pptx)"
    except Exception as e:
        return f"(pptx parse error: {type(e).__name__}: {e})"


def extract_text(file_path: str, max_chars: int = 50_000) -> dict:
    p = Path(os.path.expanduser(file_path))
    if not p.exists():
        return {"error": f"File not found: {file_path!r}"}
    if not p.is_file():
        return {"error": f"Not a regular file: {file_path!r}"}
    ext = p.suffix.lower()
    if ext in _IMAGE:
        return {"error": f"{ext} is an image file — not supported. Use a vision-capable host."}
    if ext in _AV:
        return {"error": f"{ext} is an audio/video file — not supported here. Use a transcription tool."}
    if ext not in _SUPPORTED:
        return {"error": f"Unsupported file type {ext!r}. Supported: {sorted(_SUPPORTED)}"}
    try:
        if ext in _TEXT:
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            blob = p.read_bytes()
            if ext == ".pdf": text = _extract_pdf(blob)
            elif ext == ".docx": text = _extract_docx(blob)
            elif ext == ".xlsx": text = _extract_xlsx(blob)
            elif ext == ".pptx": text = _extract_pptx(blob)
            else: text = "(unsupported)"
    except Exception as e:
        return {"error": f"Read/parse failed: {type(e).__name__}: {e}"}
    text = text or ""
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
        truncated = True
    return {
        "file_path": str(p),
        "file_name": p.name,
        "ext": ext,
        "content": text,
        "char_count": len(text),
        "truncated": truncated,
    }


_USAGE = """\
usage:
  python scripts/extract_tools.py extract_text <file_path> [max_chars=50000]

Supported: .txt .md .csv .pdf .docx .pptx .xlsx
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "extract_text":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            mx = int(argv[3]) if len(argv) > 3 else 50_000
            result: object = extract_text(argv[2], mx)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
