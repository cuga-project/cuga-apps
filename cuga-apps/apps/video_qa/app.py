"""
Video Q&A — browser web interface.

This is a thin wrapper that launches the existing run.py web UI
at a dedicated port (8771) so it doesn't conflict with voice_journal (28766).

Architecture:
  Browser  →  FastAPI (run.py _web)  →  VideoQAAgent
                                         ├── faster-whisper  (transcription)
                                         └── ChromaDB + LLM  (Q&A)

Run:
    python app.py
    python app.py --provider rits

    Then open http://127.0.0.1:8771

    1. Paste the path to a .mp4 / .m4a / .wav file
    2. Click "Transcribe"
    3. Ask questions

Required:
    pip install faster-whisper chromadb sentence-transformers fastapi uvicorn
    brew install ffmpeg
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


if __name__ == "__main__":
    import argparse
    import textwrap

    parser = argparse.ArgumentParser(
        description="Video Q&A — browser web interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python app.py
              python app.py --provider rits
              python app.py --provider openai

            Then open http://127.0.0.1:8771
        """),
    )
    parser.add_argument("--host",     default="127.0.0.1")
    parser.add_argument("--port",     type=int, default=8771)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    from run import _web
    _web(args.port, provider=args.provider, llm_model=args.model)
