"""
Box Document Q&A — web UI powered by CugaAgent
===============================================

Connect to a Box folder and ask questions across your documents.
The agent lists files, fetches and extracts text from supported document
types, and answers questions with citations to specific files.

Supported file types: PDF, DOCX, PPTX, XLSX, TXT, MD, CSV
Video/audio files are surfaced by name but not processed.

Run:
    python main.py
    python main.py --port 28810
    python main.py --provider anthropic

Then open: http://127.0.0.1:28810

Environment variables:
    LLM_PROVIDER        rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL           model override
    BOX_CONFIG_PATH     path to Box app config JSON (JWT auth)
    BOX_FOLDER_ID       Box folder ID to browse (default: "0" = root)
    AGENT_SETTING_CONFIG  path to cuga settings TOML
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Load shared .env from apps/ directory (does not override already-set vars)
try:
    from dotenv import load_dotenv
    load_dotenv(_DEMOS_DIR / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Supported file types
# ---------------------------------------------------------------------------

_DOC_TYPES = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv"}
_SKIP_TYPES = {".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".m4a", ".aac",
               ".wmv", ".flv", ".webm", ".ogg"}


# ---------------------------------------------------------------------------
# Box client factory
# ---------------------------------------------------------------------------

def _box_client():
    """Return an authenticated Box client using JWT app config."""
    try:
        from boxsdk import JWTAuth, Client
    except ImportError:
        raise RuntimeError("boxsdk not installed — run: pip install boxsdk[jwt]")

    config_path = os.getenv("BOX_CONFIG_PATH", "")
    if not config_path or not Path(config_path).exists():
        raise RuntimeError(
            "BOX_CONFIG_PATH not set or file not found. "
            "Set it to the path of your Box app config JSON."
        )

    auth = JWTAuth.from_settings_file(config_path)
    return Client(auth)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    from langchain_core.tools import tool

    @tool
    def list_box_folder(folder_id: str = "") -> str:
        """
        List files and subfolders in a Box folder.
        Returns name, type, file ID, size, and modified date for each item.
        For files, also indicates whether they are supported for Q&A (documents)
        or unsupported (video/audio).

        Args:
            folder_id: Box folder ID. Leave empty to use the configured root folder.
        """
        fid = folder_id.strip() or os.getenv("BOX_FOLDER_ID", "0")
        try:
            client = _box_client()
            folder = client.folder(fid).get()
            items  = folder.get_items(limit=100)
            results = []
            for item in items:
                entry = {
                    "id":   item.id,
                    "name": item.name,
                    "type": item.type,
                }
                if item.type == "file":
                    ext = Path(item.name).suffix.lower()
                    entry["supported"] = ext in _DOC_TYPES
                    entry["file_type"] = (
                        "document" if ext in _DOC_TYPES
                        else "video/audio (not supported in this version)"
                        if ext in _SKIP_TYPES
                        else "other"
                    )
                    try:
                        info = client.file(item.id).get()
                        entry["size_bytes"]    = info.size
                        entry["modified_at"]   = str(info.modified_at)
                        entry["description"]   = info.description or ""
                    except Exception:
                        pass
                results.append(entry)
            return json.dumps({
                "folder_name": folder.name,
                "folder_id":   fid,
                "item_count":  len(results),
                "items":       results,
            }, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @tool
    def get_file_content(file_id: str) -> str:
        """
        Download a supported document from Box and extract its text content.
        Works with PDF, DOCX, PPTX, XLSX, TXT, MD, and CSV files.
        Returns an error for video/audio files (not supported).

        Args:
            file_id: The Box file ID (from list_box_folder results).
        """
        try:
            client = _box_client()
            info   = client.file(file_id).get()
            name   = info.name
            ext    = Path(name).suffix.lower()

            if ext in _SKIP_TYPES:
                return json.dumps({
                    "error": (
                        f"'{name}' is a video/audio file. "
                        "Text extraction for media files is not supported in this version. "
                        "Only document files (PDF, DOCX, TXT, etc.) can be read."
                    )
                })

            if ext not in _DOC_TYPES:
                return json.dumps({"error": f"'{name}': unsupported file type '{ext}'."})

            log.info("Downloading %s (id=%s)", name, file_id)
            content_stream = client.file(file_id).content()

            if ext in {".txt", ".md", ".csv"}:
                text = content_stream.decode("utf-8", errors="replace")
                return json.dumps({"file_name": name, "content": text[:50_000]})

            # Extraction is delegated to mcp-text via the b64 bytes API —
            # the Box file content stays in this container's memory and is
            # streamed to mcp-text for docling conversion.
            import base64 as _b64
            from _mcp_bridge import call_tool
            try:
                payload = call_tool(
                    "text",
                    "extract_text_from_bytes",
                    {
                        "content_b64":    _b64.b64encode(content_stream).decode(),
                        "file_extension": ext,
                        "max_chars":      50_000,
                    },
                    timeout=180.0,
                )
                text = (payload or {}).get("markdown", "").strip() or "(no text extracted)"
            except RuntimeError as exc:
                text = f"(extraction error: {exc})"
            except Exception as exc:
                text = f"(extraction error: {exc})"

            return json.dumps({"file_name": name, "content": text[:50_000]})

        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @tool
    def search_box(query: str, folder_id: str = "") -> str:
        """
        Search for files in Box by name or content keyword.
        Returns matching files with their IDs so you can then fetch their content.

        Args:
            query:     Search term (filename keywords or content keywords).
            folder_id: Limit search to this folder ID (optional).
        """
        try:
            client = _box_client()
            kwargs: dict = {"query": query, "result_type": "file", "limit": 20}
            if folder_id.strip():
                kwargs["ancestor_folder_ids"] = [folder_id.strip()]
            results = client.search().query(**kwargs)
            hits = []
            for item in results:
                ext = Path(item.name).suffix.lower()
                hits.append({
                    "id":        item.id,
                    "name":      item.name,
                    "supported": ext in _DOC_TYPES,
                    "file_type": (
                        "document" if ext in _DOC_TYPES
                        else "video/audio (not supported)"
                        if ext in _SKIP_TYPES
                        else "other"
                    ),
                })
            return json.dumps({"query": query, "results": hits})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    return [list_box_folder, get_file_content, search_box]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Box Document Q&A Assistant

You help users explore and query documents stored in Box cloud storage.
You have three tools: `list_box_folder`, `get_file_content`, and `search_box`.

## How to behave

### Listing / exploring
When the user wants to see what's in a folder:
- Call `list_box_folder` with the folder ID (or empty string for the root folder).
- Present results in a clean list: name, type, whether it's readable.
- For video/audio files, note they are not supported for Q&A in this version.

### Answering questions about documents
When the user asks a question about file contents:
1. If you don't know which file to look in, call `search_box` first to find candidates.
2. Call `get_file_content` for each relevant document file.
3. Answer the question, citing the specific file and quoting relevant passages.

### Citation format
Always cite which file an answer came from:
  [filename] — "relevant quote or close paraphrase"

When answering across multiple files:
  "Both [file-a.pdf] and [report.docx] state that …"

### What NOT to do
- Never fabricate content from a file you haven't fetched.
- Never attempt to read video/audio files — explain they're not supported.
- Don't fetch a file unless the user's question actually requires its content.

## Handling unsupported files
If the user asks about a video/audio file, say:
  "This is a video/audio file. In the current version, only document files
   (PDF, DOCX, PPTX, XLSX, TXT, MD, CSV) can be read. Future versions will
   include transcript-based Q&A for media files."
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# FastAPI server
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str
    thread_id: str = "default"


class CredentialsReq(BaseModel):
    box_config_path: str = ""
    box_folder_id: str = ""


def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from ui import _HTML

    app = FastAPI(title="Box Q&A", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent_cache: list = []  # lazy singleton: populated on first /ask

    def _get_agent():
        if not _agent_cache:
            _agent_cache.append(make_agent())
        return _agent_cache[0]

    @app.post("/ask")
    async def api_ask(req: AskReq):
        q = req.question.strip()
        if not q:
            return JSONResponse({"error": "Empty question"}, status_code=400)
        try:
            result = await _get_agent().invoke(q, thread_id=req.thread_id)
            return {"answer": result.answer}
        except Exception as exc:
            log.error("Agent error: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/settings")
    async def api_settings():
        config_path = os.getenv("BOX_CONFIG_PATH", "")
        box_ok = bool(config_path and Path(config_path).exists())
        return {
            "box_configured": box_ok,
            "box_config_path": config_path,
            "folder_id": os.getenv("BOX_FOLDER_ID", "0"),
        }

    @app.post("/settings/credentials")
    async def api_credentials(req: CredentialsReq):
        if req.box_config_path and not req.box_config_path.startswith("•"):
            os.environ["BOX_CONFIG_PATH"] = req.box_config_path
            # reset agent so it picks up the new config on next /ask
            _agent_cache.clear()
        if req.box_folder_id:
            os.environ["BOX_FOLDER_ID"] = req.box_folder_id
            _agent_cache.clear()
        config_path = os.getenv("BOX_CONFIG_PATH", "")
        box_ok = bool(config_path and Path(config_path).exists())
        return {"ok": True, "box_configured": box_ok}

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    print(f"\n  Box Document Q&A  →  http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Box Document Q&A — web UI")
    parser.add_argument("--port", type=int, default=28810)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    if not os.getenv("BOX_CONFIG_PATH"):
        print("  ⚠  BOX_CONFIG_PATH not set — Box tools will fail until configured.\n")

    _web(args.port)


if __name__ == "__main__":
    main()
