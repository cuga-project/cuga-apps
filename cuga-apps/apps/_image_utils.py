"""
Shared image utilities for cuga demo apps.

Two approaches for giving an LLM access to image content:

1. Docling extraction (recommended) — convert image/PDF to markdown offline,
   then send to any text LLM.  No vision-capable model required.

       from _image_utils import extract_with_docling
       markdown = extract_with_docling("screenshot.png")
       # → pass markdown as plain text to any CugaAgent

2. Multimodal embedding — encode as base64 data URL and embed directly in a
   LangChain HumanMessage.  Requires a vision-capable LLM (Claude 3+, GPT-4o,
   LLaVA).

       from _image_utils import make_image_message
       msg = make_image_message("screenshot.png", "What's on this screen?")
       result = await agent.invoke([msg], thread_id="img-thread")
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from langchain_core.messages import HumanMessage

_SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


# ---------------------------------------------------------------------------
# Docling extraction (works with any text LLM — no vision model needed)
# ---------------------------------------------------------------------------

def extract_with_docling(image_path: str | Path) -> str:
    """
    Convert an image or PDF to clean markdown using docling (offline OCR).

    Works with PNG, JPEG, TIFF, BMP, GIF, and PDF files.
    Preserves tables, code blocks, headings, and key-value fields.

    Returns plain markdown text that can be sent to any text-capable LLM.
    No vision model required.

    Args:
        image_path: Path to the image or PDF file.

    Raises:
        ImportError:       If docling is not installed.
        FileNotFoundError: If the file does not exist.

    Example:
        markdown = extract_with_docling("screenshot.png")
        result = await agent.invoke(
            [HumanMessage(content=f"Here is the content:\\n{markdown}\\n\\nYour question.")],
            thread_id="img-session",
        )
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        raise ImportError(
            "docling is not installed.\n"
            "  pip install docling\n"
            "See: https://github.com/docling-project/docling"
        )

    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        converter = DocumentConverter()
        result    = converter.convert(str(path))
        markdown  = result.document.export_to_markdown()
    except Exception as e:
        return f"(docling could not process this file: {e})"

    if not markdown.strip():
        return "(docling extracted no text — the image may be purely graphical or blank)"

    return markdown


def image_to_data_url(image_path: str | Path) -> str:
    """
    Encode a local image file as a base64 data URL.

    Returns a string like: ``data:image/png;base64,<base64-data>``

    Args:
        image_path: Path to the image file (PNG, JPEG, GIF, WebP, BMP, TIFF).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError:        If the file extension is not a supported image type.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    ext = path.suffix.lower()
    if ext not in _SUPPORTED_EXTS:
        raise ValueError(
            f"Unsupported image extension: {ext!r}. "
            f"Supported: {sorted(_SUPPORTED_EXTS)}"
        )

    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/png" if ext == ".png" else "image/jpeg"

    data = path.read_bytes()
    b64  = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def make_image_message(image_path: str | Path, text: str = "") -> HumanMessage:
    """
    Build a multimodal LangChain HumanMessage containing an image and text.

    The message content is a list in the format expected by vision-capable
    LangChain chat models (OpenAI, Anthropic, Google, etc.):

        [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
            {"type": "text",      "text": "<your question>"},
        ]

    Args:
        image_path: Path to the image file.
        text:       The text part of the message (question or instruction).
                    Defaults to an empty string (just send the image).

    Returns:
        HumanMessage ready to pass to ``CugaAgent.invoke([msg], thread_id=...)``.

    Example:
        result = await agent.invoke(
            [make_image_message("screenshot.png", "What error is shown here?")],
            thread_id="img-session",
        )
    """
    data_url = image_to_data_url(image_path)
    content: list = [{"type": "image_url", "image_url": {"url": data_url}}]
    if text:
        content.append({"type": "text", "text": text})
    return HumanMessage(content=content)
