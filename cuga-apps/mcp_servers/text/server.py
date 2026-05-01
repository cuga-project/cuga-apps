"""mcp-text — text transformation primitives.

Tools:
  - chunk_text(text, strategy, size, overlap)   stateless splitting
  - count_tokens(text, encoding)                tiktoken encoding count
  - extract_text(file_path)                     docling: PDF/DOCX/XLSX/HTML → markdown

All three are pure transformations — no shared state. Apps that previously
reimplemented chunking, token counting, or document extraction can drop those
dependencies and call this server instead.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_TEXT_PORT  # noqa: E402

mcp = make_server("mcp-text")


# ── chunk_text ──────────────────────────────────────────────────────────

_RECURSIVE_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _chunk_fixed_chars(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks


def _chunk_recursive(text: str, size: int, overlap: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text] if text else []
    sep = next((s for s in seps if s and s in text), "")
    if not sep:
        return _chunk_fixed_chars(text, size, overlap)
    parts = text.split(sep)
    chunks: list[str] = []
    buf: list[str] = []
    cur_len = 0
    for part in parts:
        piece = part + (sep if part is not parts[-1] else "")
        if cur_len + len(piece) > size and buf:
            chunks.append("".join(buf))
            tail_overlap = "".join(buf)[-overlap:] if overlap > 0 else ""
            buf = [tail_overlap, piece] if tail_overlap else [piece]
            cur_len = len(buf[0]) + (len(buf[1]) if len(buf) > 1 else 0)
        else:
            buf.append(piece)
            cur_len += len(piece)
    if buf:
        chunks.append("".join(buf))
    out: list[str] = []
    for c in chunks:
        if len(c) > size * 1.5:
            sub_seps = seps[seps.index(sep) + 1:] if sep in seps else []
            out.extend(_chunk_recursive(c, size, overlap, sub_seps))
        else:
            out.append(c)
    return [c for c in out if c]


def _chunk_markdown_headers(text: str, size: int) -> list[str]:
    blocks: list[str] = []
    cur: list[str] = []
    for line in text.splitlines(keepends=True):
        if re.match(r"^#{1,6}\s", line) and cur:
            blocks.append("".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("".join(cur))
    out: list[str] = []
    for b in blocks:
        if len(b) <= size:
            out.append(b)
        else:
            out.extend(_chunk_fixed_chars(b, size, max(50, size // 10)))
    return [c for c in out if c.strip()]


@mcp.tool()
def chunk_text(
    text: str,
    strategy: str = "recursive",
    size: int = 800,
    overlap: int = 100,
) -> str:
    """Split a long text into chunks using the requested strategy.

    Use this before embedding/indexing documents, or to fit long inputs into
    an LLM context window. Stateless — no caching, no storage.

    Args:
        text: Input text.
        strategy: "recursive" (default — splits on \\n\\n / \\n / sentence / word
                  boundaries until each chunk fits), "fixed_chars" (uniform
                  character windows with overlap), "markdown_headers" (splits
                  on `#` / `##` / etc; falls back to fixed within long sections).
        size: Target chunk size in characters (default 800).
        overlap: Overlap in characters between adjacent chunks (default 100).
                 Ignored by markdown_headers.

    Returns:
        {chunks: [str, ...], count: int, strategy: str, size: int}
    """
    if not text:
        return tool_result({"chunks": [], "count": 0, "strategy": strategy, "size": size})
    if strategy == "fixed_chars":
        chunks = _chunk_fixed_chars(text, size, overlap)
    elif strategy == "markdown_headers":
        chunks = _chunk_markdown_headers(text, size)
    elif strategy in ("recursive", "fixed_tokens"):
        # fixed_tokens uses recursive char split — true tokenization is in count_tokens.
        chunks = _chunk_recursive(text, size, overlap, _RECURSIVE_SEPARATORS)
    else:
        return tool_error(
            f"Unknown strategy: {strategy!r}. Choose recursive, fixed_chars, or markdown_headers.",
            code="bad_input",
        )
    return tool_result({
        "chunks":   chunks,
        "count":    len(chunks),
        "strategy": strategy,
        "size":     size,
        "overlap":  overlap if strategy != "markdown_headers" else 0,
    })


# ── count_tokens ────────────────────────────────────────────────────────

@mcp.tool()
def count_tokens(text: str, encoding: str = "cl100k_base") -> str:
    """Count tokens in a string using a tiktoken encoding.

    cl100k_base matches GPT-4 / GPT-3.5-turbo / text-embedding-3 family.
    o200k_base matches GPT-4o. Use this to size requests before sending
    them to an LLM, or to estimate cost.

    Args:
        text: Text to tokenize.
        encoding: tiktoken encoding name (default "cl100k_base").

    Returns:
        {token_count: int, encoding: str, char_count: int}
    """
    try:
        import tiktoken
    except ImportError:
        return tool_error("tiktoken not installed on the MCP server.", code="missing_dep")
    try:
        enc = tiktoken.get_encoding(encoding)
    except Exception as exc:
        return tool_error(f"Unknown encoding {encoding!r}: {exc}", code="bad_input")
    tokens = enc.encode(text or "")
    return tool_result({
        "token_count": len(tokens),
        "encoding":    encoding,
        "char_count":  len(text or ""),
    })


# ── extract_text ────────────────────────────────────────────────────────

@mcp.tool()
def extract_text(file_path: str, max_chars: int = 200_000) -> str:
    """Extract text content from a document file via docling.

    Supports PDF, DOCX, XLSX, PPTX, HTML, MD, images (with OCR), and others
    docling can decode. Returns markdown text plus brief metadata.

    The file must be readable at file_path from inside the MCP server's
    container — bind-mount the host path if you're calling from outside.

    Args:
        file_path: Absolute path to the document.
        max_chars: Truncate the returned markdown at this many characters
                   (default 200000) to avoid blowing up the LLM context.

    Returns:
        {path, markdown, char_count, truncated, page_count?}
    """
    p = Path(file_path).expanduser()
    if not p.exists():
        return tool_error(f"File not found: {file_path}", code="not_found")
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return tool_error("docling not installed on the MCP server.", code="missing_dep")
    try:
        conv = DocumentConverter()
        result = conv.convert(str(p))
        md = result.document.export_to_markdown() or ""
        truncated = len(md) > max_chars
        if truncated:
            md = md[:max_chars] + "\n\n…[truncated]"
        page_count = None
        try:
            page_count = len(getattr(result.document, "pages", []))
        except Exception:
            pass
        return tool_result({
            "path":       str(p),
            "markdown":   md,
            "char_count": len(md),
            "truncated":  truncated,
            "page_count": page_count,
        })
    except Exception as exc:
        return tool_error(f"docling conversion failed: {exc}", code="upstream")


@mcp.tool()
def extract_text_from_bytes(
    content_b64: str,
    file_extension: str,
    max_chars: int = 200_000,
) -> str:
    """Extract text from a file uploaded as base64 bytes.

    Use this when the file lives in the caller's filesystem (e.g. a tmp file
    inside another container) and isn't directly readable by this MCP server.
    The bytes are written to a temp file inside the server, converted with
    docling, then cleaned up. For files already on a shared filesystem,
    prefer extract_text(file_path) — it's faster and avoids the b64 round-trip.

    Args:
        content_b64: Base64-encoded file bytes.
        file_extension: Extension including the dot (e.g. ".pdf", ".docx").
                         docling uses this to pick the right backend.
        max_chars: Truncate returned markdown at this length (default 200000).

    Returns:
        {filename, markdown, char_count, truncated, page_count?}
    """
    import base64
    import tempfile
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return tool_error("docling not installed on the MCP server.", code="missing_dep")
    try:
        raw = base64.b64decode(content_b64)
    except Exception as exc:
        return tool_error(f"Invalid base64: {exc}", code="bad_input")
    suffix = file_extension if file_extension.startswith(".") else "." + file_extension
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        result = DocumentConverter().convert(tmp.name)
        md = result.document.export_to_markdown() or ""
        truncated = len(md) > max_chars
        if truncated:
            md = md[:max_chars] + "\n\n…[truncated]"
        page_count = None
        try:
            page_count = len(getattr(result.document, "pages", []))
        except Exception:
            pass
        return tool_result({
            "filename":   Path(tmp.name).name,
            "markdown":   md,
            "char_count": len(md),
            "truncated":  truncated,
            "page_count": page_count,
        })
    except Exception as exc:
        return tool_error(f"docling conversion failed: {exc}", code="upstream")
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    run(mcp, MCP_TEXT_PORT)
