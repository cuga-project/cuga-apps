"""CLI helpers for the box_qa skill.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/box_tools.py list_box_folder 0
    python scripts/box_tools.py search_box 'Q3 forecast'
    python scripts/box_tools.py get_file_content 1234567890

Env (required):
  BOX_CONFIG_PATH  — path to the Box app config JSON (JWT auth)
  BOX_FOLDER_ID    — default folder to browse (defaults to "0" / root)

Pip deps (declared in SKILL.md frontmatter):
  boxsdk[jwt]>=3.10  — Box Python SDK with JWT auth
  pypdf>=4.0         — PDF text extraction
  python-docx>=1.1   — DOCX text extraction

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

_DOC_TYPES = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv"}
_SKIP_TYPES = {".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".m4a",
               ".aac", ".wmv", ".flv", ".webm", ".ogg"}


def _box_client():
    """Authenticated Box client via JWT app config."""
    try:
        from boxsdk import JWTAuth, Client
    except ImportError as e:
        raise RuntimeError(
            "boxsdk not installed (declared in SKILL.md requirements as boxsdk[jwt])"
        ) from e
    config_path = os.getenv("BOX_CONFIG_PATH", "")
    if not config_path or not Path(config_path).exists():
        raise RuntimeError("BOX_CONFIG_PATH not set or file not found")
    auth = JWTAuth.from_settings_file(config_path)
    return Client(auth)


def _classify(name: str) -> tuple[bool, str]:
    ext = Path(name).suffix.lower()
    if ext in _DOC_TYPES:
        return True, "document"
    if ext in _SKIP_TYPES:
        return False, "video/audio (not supported)"
    return False, "other"


def list_box_folder(folder_id: str = "") -> dict:
    fid = (folder_id or "").strip() or os.getenv("BOX_FOLDER_ID", "0")
    try:
        client = _box_client()
        folder = client.folder(fid).get()
        items = folder.get_items(limit=100)
    except Exception as e:
        return {"error": f"Box list failed: {type(e).__name__}: {e}"}
    results = []
    for item in items:
        entry = {"id": item.id, "name": item.name, "type": item.type}
        if item.type == "file":
            supported, kind = _classify(item.name)
            entry["supported"] = supported
            entry["file_type"] = kind
            try:
                info = client.file(item.id).get()
                entry["size_bytes"] = info.size
                entry["modified_at"] = str(info.modified_at)
                entry["description"] = info.description or ""
            except Exception:
                pass
        results.append(entry)
    return {
        "folder_name": folder.name,
        "folder_id": fid,
        "item_count": len(results),
        "items": results,
    }


def search_box(query: str, folder_id: str = "") -> dict:
    try:
        client = _box_client()
        kwargs: dict = {"query": query, "result_type": "file", "limit": 20}
        if folder_id.strip():
            kwargs["ancestor_folder_ids"] = [folder_id.strip()]
        results = client.search().query(**kwargs)
        hits = []
        for item in results:
            supported, kind = _classify(item.name)
            hits.append({
                "id": item.id,
                "name": item.name,
                "supported": supported,
                "file_type": kind,
            })
        return {"query": query, "results": hits}
    except Exception as e:
        return {"error": f"Box search failed: {type(e).__name__}: {e}"}


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
    """Stdlib XLSX: read sharedStrings + each sheet's <c><v> cells."""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            shared: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                for si in root.findall("x:si", ns):
                    parts = [t.text or "" for t in si.findall(".//x:t", ns)]
                    shared.append("".join(parts))
            sheet_names = [n for n in z.namelist()
                           if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
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
    """Stdlib PPTX: read each slide's <a:t> text runs."""
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


def get_file_content(file_id: str) -> dict:
    try:
        client = _box_client()
        info = client.file(file_id).get()
    except Exception as e:
        return {"error": f"Box file lookup failed: {type(e).__name__}: {e}"}
    name = info.name
    ext = Path(name).suffix.lower()
    if ext in _SKIP_TYPES:
        return {"error": f"{name!r} is a video/audio file — not supported"}
    if ext not in _DOC_TYPES:
        return {"error": f"{name!r}: unsupported file type {ext!r}"}
    try:
        blob = client.file(file_id).content()
    except Exception as e:
        return {"error": f"Box download failed: {type(e).__name__}: {e}"}
    if ext in {".txt", ".md", ".csv"}:
        text = blob.decode("utf-8", errors="replace")
    elif ext == ".pdf":
        text = _extract_pdf(blob)
    elif ext == ".docx":
        text = _extract_docx(blob)
    elif ext == ".xlsx":
        text = _extract_xlsx(blob)
    elif ext == ".pptx":
        text = _extract_pptx(blob)
    else:
        text = "(unsupported)"
    return {"file_name": name, "content": text[:50_000]}


_USAGE = """\
usage:
  python scripts/box_tools.py list_box_folder [folder_id]
  python scripts/box_tools.py search_box <query> [folder_id]
  python scripts/box_tools.py get_file_content <file_id>

Required env: BOX_CONFIG_PATH (path to JWT app config JSON)
Optional env: BOX_FOLDER_ID (default folder, "0" = root)
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "list_box_folder":
            fid = argv[2] if len(argv) > 2 else ""
            result: object = list_box_folder(fid)
        elif cmd == "search_box":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            fid = argv[3] if len(argv) > 3 else ""
            result = search_box(argv[2], fid)
        elif cmd == "get_file_content":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            result = get_file_content(argv[2])
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
