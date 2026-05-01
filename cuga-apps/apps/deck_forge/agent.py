"""
DeckForge agent implementations — LangGraph ReAct and CugaAgent.

Both agents share the same five tool closures (_make_tools) so the tool
behaviour, progress events, and output format are identical regardless of
which backend runs.  The only difference is how the agent loop is driven:

  LangGraph ReAct  — astream() with stream_mode="updates"; full streaming.
  CugaAgent        — ainvoke(); single round-trip per invocation.

Agent tool interface (shared)
------------------------------
  list_directory(directory)           → manifest of supported files
  extract_and_index(filepath)         → extract + RAG-index one file
  search_knowledge_base(query, n)     → retrieve relevant chunks
  add_slide(title, bullets, notes)    → append slide to session
  finalize(deck_title, deck_subtitle) → write PPTX + MD, emit done event
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# Add demo_apps parent so _llm.py is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from session import DeckForgeSession

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are DeckForge, an AI presentation architect.  Your job is to examine a \
directory of source materials (PDFs, slides, text, recordings) and produce \
a polished, well-structured presentation on a given topic.

Your process — follow it exactly:
1. DISCOVER   Call list_directory to see all available files.
2. INGEST     Call extract_and_index for every relevant file.
              Skip files whose names or types make them clearly off-topic.
3. ASSESS     Call search_knowledge_base with 2-3 broad topic queries to
              gauge available content and spot key themes.
4. STRUCTURE  Reason about a narrative arc: opening → context → deep dives
              → synthesis → key takeaways.  Plan 7-11 content slides.
5. BUILD      For each planned slide call search_knowledge_base with a
              focused query, then call add_slide with well-crafted bullets.
6. FINALIZE   Call finalize to write the output files.

Slide writing guidelines
------------------------
- Bullets: 4-6 per slide, each 10-15 words, starting with an action verb or
  key noun phrase.
- Speaker notes: 2-4 sentences citing specific source material.
- First content slide: "Overview" or "Agenda".
- Last content slide: "Key Takeaways" with 4-5 crisp conclusions.
- Synthesise overlapping content — never repeat the same point on two slides.
"""


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def _make_tools(session: DeckForgeSession) -> list:
    """Return async tools closed over the given session."""

    # ------------------------------------------------------------------ #
    # 1. list_directory                                                    #
    # ------------------------------------------------------------------ #
    @tool
    async def list_directory(directory: str) -> str:
        """List all files in directory and classify them by type.
        Call this first to discover what source material is available."""
        from extractors import classify_file, SUPPORTED_EXTENSIONS

        p = Path(directory)
        if not p.exists():
            return f"ERROR: directory does not exist: {directory}"
        if not p.is_dir():
            return f"ERROR: not a directory: {directory}"

        files = sorted(p.rglob("*"))
        manifest: list[dict] = []
        skipped = 0
        for f in files:
            if not f.is_file():
                continue
            ftype = classify_file(str(f))
            if ftype:
                manifest.append({
                    "path": str(f),
                    "name": f.name,
                    "type": ftype,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                })
            else:
                skipped += 1

        await session.queue.put({
            "type": "directory_scanned",
            "file_count": len(manifest),
            "skipped": skipped,
            "files": [{"name": m["name"], "type": m["type"]} for m in manifest],
        })

        if not manifest:
            return (
                f"No supported files found in {directory}. "
                f"({skipped} unsupported files ignored)"
            )

        lines = [f"Found {len(manifest)} supported file(s):"]
        for m in manifest:
            lines.append(f"  [{m['type']:8s}] {m['name']}  ({m['size_kb']} KB)  path={m['path']}")
        if skipped:
            lines.append(f"  ({skipped} unsupported files ignored)")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 2. extract_and_index                                                 #
    # ------------------------------------------------------------------ #
    @tool
    async def extract_and_index(filepath: str) -> str:
        """Extract text from filepath (PDF/PPTX/MD/TXT/audio/video) and index
        it into the session knowledge base for later retrieval.
        Call this for each relevant file discovered by list_directory."""
        from extractors import extract, classify_file

        ftype = classify_file(filepath)
        if ftype is None:
            return f"Unsupported file type: {filepath}"

        await session.queue.put({
            "type": "extracting",
            "file": Path(filepath).name,
            "file_type": ftype,
        })

        try:
            _, text = await asyncio.to_thread(extract, filepath)
        except Exception as exc:
            msg = f"Extraction failed for {Path(filepath).name}: {exc}"
            await session.queue.put({"type": "extract_error", "file": Path(filepath).name, "error": str(exc)})
            return msg

        if not text.strip():
            return f"No text content extracted from {Path(filepath).name}"

        n_chunks = await asyncio.to_thread(session.kb.add_document, filepath, text)

        await session.queue.put({
            "type": "indexed",
            "file": Path(filepath).name,
            "file_type": ftype,
            "chunks": n_chunks,
            "total_chunks": session.kb.chunk_count,
        })

        preview = text[:150].replace("\n", " ")
        return (
            f"OK: indexed '{Path(filepath).name}' ({ftype}) → {n_chunks} chunks. "
            f"KB total: {session.kb.chunk_count}. Preview: {preview}"
        )

    # ------------------------------------------------------------------ #
    # 3. search_knowledge_base                                             #
    # ------------------------------------------------------------------ #
    @tool
    async def search_knowledge_base(
        query: str,
        n_results: Annotated[int, "Number of chunks to retrieve (1-10)"] = 5,
    ) -> str:
        """Semantic search over all indexed documents.
        Use specific, focused queries to find content relevant to each slide."""
        if session.kb.chunk_count == 0:
            return "Knowledge base is empty — call extract_and_index first."

        results = await asyncio.to_thread(
            session.kb.search, query, min(n_results, 10)
        )
        if not results:
            return f"No results found for query: {query!r}"

        await session.queue.put({
            "type": "search",
            "query": query,
            "hits": len(results),
        })

        lines = [f"Search '{query}' → {len(results)} hit(s):"]
        for i, r in enumerate(results, start=1):
            src = Path(r["source"]).name
            lines.append(
                f"[{i}] {src}  {r['text'][:220].replace(chr(10), ' ')}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 4. add_slide                                                         #
    # ------------------------------------------------------------------ #
    @tool
    async def add_slide(
        title: str,
        bullets: Annotated[str, "Bullet points, one per line"],
        speaker_notes: Annotated[str, "Speaker notes paragraph (optional)"] = "",
    ) -> str:
        """Add one slide to the presentation being built.
        Bullets should be newline-separated, 4-6 bullets per slide."""
        from deck_writer import Slide

        bullet_list = [b.lstrip("•-* ").strip() for b in bullets.splitlines() if b.strip()]
        slide = Slide(title=title, bullets=bullet_list, speaker_notes=speaker_notes)
        session.slides.append(slide)

        await session.queue.put({
            "type": "slide_added",
            "num": len(session.slides),
            "title": title,
            "bullet_count": len(bullet_list),
        })

        return f"Slide {len(session.slides)} added: '{title}' ({len(bullet_list)} bullets)"

    # ------------------------------------------------------------------ #
    # 5. finalize                                                          #
    # ------------------------------------------------------------------ #
    @tool
    async def finalize(
        deck_title: str,
        deck_subtitle: Annotated[str, "Subtitle for the title slide (optional)"] = "",
    ) -> str:
        """Save the completed presentation as deck.pptx and deck.md.
        Call this after all slides have been added via add_slide."""
        from deck_writer import Deck, build_pptx, build_markdown

        if not session.slides:
            return "ERROR: No slides have been added yet."

        deck = Deck(title=deck_title, subtitle=deck_subtitle, slides=session.slides)
        pptx_path = str(session.output_dir / "deck.pptx")
        md_path   = str(session.output_dir / "deck.md")

        await asyncio.to_thread(build_pptx, deck, pptx_path)
        await asyncio.to_thread(build_markdown, deck, md_path)

        session.status = "done"
        session.result = {
            "pptx": pptx_path,
            "md":   md_path,
            "slide_count": len(session.slides),
        }

        await session.queue.put({
            "type": "done",
            "slide_count": len(session.slides),
            "pptx_filename": "deck.pptx",
            "md_filename":   "deck.md",
        })

        return (
            f"Done!  {len(session.slides)} slides saved.\n"
            f"  PPTX: {pptx_path}\n"
            f"  MD:   {md_path}"
        )

    return [list_directory, extract_and_index, search_knowledge_base, add_slide, finalize]


# ---------------------------------------------------------------------------
# Public: build agent graph
# ---------------------------------------------------------------------------

def build_langgraph_agent(session: DeckForgeSession, llm):
    """Compile and return a LangGraph ReAct agent for this session."""
    tools = _make_tools(session)
    return create_react_agent(llm, tools, prompt=_SYSTEM)


# ---------------------------------------------------------------------------
# Public: run agent (called from main.py as an asyncio task)
# ---------------------------------------------------------------------------

_AGENT_PROMPT_TEMPLATE = """\
Topic: {topic}
Source directory: {directory}

Please follow your process to generate a complete presentation deck.
Start by listing the directory.
"""


async def run_langgraph_agent(session: DeckForgeSession) -> None:
    """
    LangGraph ReAct runner.  Streams graph update events and converts them
    into progress messages pushed to session.queue.
    """
    from _llm import create_llm

    session.status = "running"
    await session.queue.put({
        "type": "start",
        "topic": session.topic,
        "directory": session.directory,
    })

    try:
        llm = await asyncio.to_thread(create_llm)
    except Exception as exc:
        session.status = "error"
        session.error  = str(exc)
        await session.queue.put({"type": "error", "message": f"LLM init failed: {exc}"})
        return

    user_msg = HumanMessage(
        content=_AGENT_PROMPT_TEMPLATE.format(
            topic=session.topic,
            directory=session.directory,
        )
    )

    # Retry on transient API errors (e.g. 'choices' KeyError from an empty
    # RITS response, 429 rate-limits, network blips).
    # Each retry rebuilds the agent graph with a fresh KB so ingestion re-runs.
    _MAX_RETRIES = 3
    for _attempt in range(_MAX_RETRIES):
        session.slides.clear()
        from rag import KnowledgeBase
        session.kb = KnowledgeBase(f"{session.session_id}_a{_attempt}")
        agent_graph = build_langgraph_agent(session, llm)
        _last_exc: Exception | None = None

        try:
            await _run_stream(agent_graph, session, user_msg)
        except Exception as exc:
            _last_exc = exc

        if session.status == "done":
            return

        if _attempt < _MAX_RETRIES - 1:
            await session.queue.put({
                "type": "thought",
                "node": "system",
                "content": (
                    f"Transient error on attempt {_attempt + 1}/{_MAX_RETRIES}: "
                    f"{_last_exc or session.error}. Retrying…"
                ),
            })
            session.status = "running"
            session.error = None
            await asyncio.sleep(1)

    # All retries exhausted
    if session.status != "done":
        session.status = "error"
        if not session.error:
            session.error = "Agent failed after all retries"
        await session.queue.put({"type": "error", "message": session.error})


async def _run_stream(agent_graph, session: DeckForgeSession, user_msg: HumanMessage) -> None:
    """Single execution pass of the LangGraph agent.  Raises on transient errors."""
    try:
        async for update in agent_graph.astream(
            {"messages": [user_msg]},
            stream_mode="updates",
            config={"recursion_limit": 120},
        ):
            for node_name, node_output in update.items():
                msgs = node_output.get("messages", [])
                for msg in msgs:
                    # AI reasoning (text without tool calls)
                    if (
                        hasattr(msg, "content")
                        and isinstance(msg.content, str)
                        and msg.content.strip()
                        and not getattr(msg, "tool_calls", None)
                    ):
                        await session.queue.put({
                            "type": "thought",
                            "node": node_name,
                            "content": msg.content[:600],
                        })
                    # AI dispatching tool calls
                    if getattr(msg, "tool_calls", None):
                        for tc in msg.tool_calls:
                            await session.queue.put({
                                "type": "tool_call",
                                "tool": tc["name"],
                                "args_preview": _truncate_args(tc.get("args", {})),
                            })

    except Exception as exc:
        # Propagate to caller so the retry loop can handle it
        if session.status != "done":
            session.error = str(exc)
        raise

    # If the stream completed but finalize was never called, treat as an error
    # so the retry loop can try again
    if session.status == "running":
        session.error = "Agent finished without calling finalize()"
        raise RuntimeError(session.error)


# ---------------------------------------------------------------------------
# CugaAgent builder
# ---------------------------------------------------------------------------

async def build_cuga_agent(session: DeckForgeSession, llm):
    """Initialise and return a CugaAgent for this session."""
    from cuga.sdk import CugaAgent

    # CugaAgent validates OPENAI_API_KEY internally even when a custom model
    # is supplied — set a placeholder so the check passes without routing traffic.
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-placeholder-not-used"

    tools = _make_tools(session)
    agent = CugaAgent(model=llm, tools=tools, special_instructions=_SYSTEM)
    await agent.initialize()
    return agent


# ---------------------------------------------------------------------------
# CugaAgent runner
# ---------------------------------------------------------------------------

async def run_cuga_agent(session: DeckForgeSession) -> None:
    """
    Entry point for CugaAgent runs.  CugaAgent uses ainvoke() rather than
    streaming, so progress events come exclusively from the tool closures.
    After the invoke returns we emit a thought with the final answer.
    """
    from _llm import create_llm

    session.status = "running"
    await session.queue.put({
        "type": "start",
        "topic": session.topic,
        "directory": session.directory,
    })

    try:
        llm = await asyncio.to_thread(create_llm)
    except Exception as exc:
        session.status = "error"
        session.error  = str(exc)
        await session.queue.put({"type": "error", "message": f"LLM init failed: {exc}"})
        return

    prompt = _AGENT_PROMPT_TEMPLATE.format(
        topic=session.topic,
        directory=session.directory,
    )

    _MAX_RETRIES = 3
    for _attempt in range(_MAX_RETRIES):
        session.slides.clear()
        from rag import KnowledgeBase
        session.kb = KnowledgeBase(f"{session.session_id}_c{_attempt}")
        cuga = None

        try:
            cuga = await build_cuga_agent(session, llm)
            result = await cuga.invoke(prompt, thread_id=session.session_id)

            if result.error:
                raise RuntimeError(result.error)

            # Emit the final answer as a thought so the UI shows it
            if result.answer:
                await session.queue.put({
                    "type": "thought",
                    "node": "cuga",
                    "content": result.answer[:600],
                })

        except Exception as exc:
            if session.status != "done":
                session.error = str(exc)
        finally:
            if cuga is not None:
                try:
                    await cuga.aclose()
                except Exception:
                    pass

        if session.status == "done":
            return

        if _attempt < _MAX_RETRIES - 1:
            await session.queue.put({
                "type": "thought",
                "node": "system",
                "content": (
                    f"Transient error on attempt {_attempt + 1}/{_MAX_RETRIES}: "
                    f"{session.error}. Retrying…"
                ),
            })
            session.status = "running"
            session.error = None
            await asyncio.sleep(1)

    if session.status != "done":
        session.status = "error"
        if not session.error:
            session.error = "CugaAgent failed after all retries"
        await session.queue.put({"type": "error", "message": session.error})


# ---------------------------------------------------------------------------
# Unified entry point — dispatches on session.agent_type
# ---------------------------------------------------------------------------

async def run_agent(session: DeckForgeSession) -> None:
    """Dispatch to LangGraph or CugaAgent based on session.agent_type."""
    if session.agent_type == "cuga":
        await run_cuga_agent(session)
    else:
        await run_langgraph_agent(session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_args(args: dict, max_len: int = 150) -> str:
    text = ", ".join(f"{k}={str(v)!r}" for k, v in args.items())
    return text[:max_len] + "…" if len(text) > max_len else text
