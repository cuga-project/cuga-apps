"""Ouroboros end-to-end diagnostic.

Boots the supervisor, sends one /ask, and dumps EVERY intermediate code
block the supervisor's planner wrote, so we can see exactly where the
cascade derails.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    export LLM_PROVIDER=anthropic
    export CUGA_TARGET=ce
    .venv/bin/python diag.py 'find restaurants in pleasantville NY'

Dumps to:
    /tmp/ouroboros_diag.log    full server-side log
    /tmp/ouroboros_diag.txt    just the supervisor's code blocks + final answer
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import textwrap
from pathlib import Path

_DIR = Path(__file__).parent
sys.path.insert(0, str(_DIR))
sys.path.insert(0, str(_DIR.parent))

os.environ.setdefault("CUGA_TARGET", "ce")

# ── Configure logging: full detail to file, summary to console
_LOG_FILE = "/tmp/ouroboros_diag.log"
_TXT_FILE = "/tmp/ouroboros_diag.txt"

_root = logging.getLogger()
_root.setLevel(logging.DEBUG)
_fh = logging.FileHandler(_LOG_FILE, mode="w")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
_root.addHandler(_fh)
_ch = logging.StreamHandler()
_ch.setLevel(logging.WARNING)
_ch.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
_root.addHandler(_ch)

log = logging.getLogger("diag")
log.setLevel(logging.INFO)


async def main(question: str) -> int:
    log.info("=== Ouroboros diagnostic ===")
    log.info(f"question={question!r}")

    from main import make_supervisor, _attach_policies, _TASK_PRELUDE

    supervisor = make_supervisor()
    await _attach_policies(supervisor)
    log.info("specialists: %s", list(getattr(supervisor, "_agents", {}).keys()))

    augmented = (
        f"{_TASK_PRELUDE}{question}\n\n"
        f"[session:(empty)] [thread:diag-1]"
    )

    # Run.
    log.info("invoking supervisor (this will hit the LLM)…")
    try:
        result = await supervisor.invoke(augmented, thread_id="diag-1")
    except Exception as exc:
        log.exception("supervisor.invoke raised")
        print(f"\n[INVOKE FAILED] {exc}\n")
        return 1

    answer = result.answer if hasattr(result, "answer") else str(result)

    # Pull every code block + every "Execution output" message from the
    # supervisor's chat history. The chat messages live on the
    # SupervisorState the SDK stored after invoke.
    state = getattr(supervisor, "_supervisor_state", None) or {}
    if hasattr(state, "supervisor_chat_messages"):
        msgs = state.supervisor_chat_messages
    elif isinstance(state, dict):
        msgs = state.get("supervisor_chat_messages", []) or []
    else:
        msgs = []

    txt_lines: list[str] = []

    def write(s: str) -> None:
        print(s)
        txt_lines.append(s)

    write("=" * 78)
    write(f"QUESTION: {question}")
    write("=" * 78)
    write(f"\nSpecialists registered: {list(getattr(supervisor, '_agents', {}).keys())}")
    write(f"Policies attached on writer: see /tmp/ouroboros_diag.log\n")

    write("=" * 78)
    write(f"SUPERVISOR CHAT TRACE  ({len(msgs)} messages)")
    write("=" * 78)

    for i, m in enumerate(msgs):
        role = type(m).__name__
        content = getattr(m, "content", "") or ""
        if not content.strip():
            continue
        write(f"\n--- Message {i}: {role}  ({len(content)} chars) ---")
        if len(content) <= 1200:
            write(content)
        else:
            # First 600, then ellipsis, then last 400 — preserves both code
            # block headers and final results.
            write(content[:600])
            write(f"\n[…{len(content) - 1000} chars elided…]\n")
            write(content[-400:])

    write("\n" + "=" * 78)
    write("FINAL ANSWER (what /ask returns to the UI)")
    write("=" * 78)
    write(answer or "(empty)")

    # Also try to extract any fenced JSON block.
    m = re.search(r"```json\s*\n(.*?)\n```", answer or "", re.DOTALL | re.IGNORECASE)
    if m:
        try:
            parsed = json.loads(m.group(1))
            n_leads = len(parsed.get("leads", []) or [])
            write(f"\n✅ Final answer contains a fenced ```json``` block — {n_leads} leads.")
        except json.JSONDecodeError as e:
            write(f"\n⚠️  Fenced ```json``` block present but unparseable: {e}")
    else:
        write("\n❌ Final answer has NO fenced ```json``` block — UI won't render anything.")

    Path(_TXT_FILE).write_text("\n".join(txt_lines))
    print(f"\n[diagnostic saved to {_TXT_FILE} and {_LOG_FILE}]")
    return 0


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "find restaurants in pleasantville NY"
    sys.exit(asyncio.run(main(q)))
