"""
VideoQAAgent — CugaAgent-backed video Q&A with timestamps.

Transcription is done explicitly via VideoQAAgent.transcribe() before Q&A —
it runs Whisper locally and can take minutes, which exceeds the agent's
code-executor timeout. The agent only gets the two fast tools:
  search_transcript   — semantic search → returns segments with timestamps
  get_segment_at_time — what was said at a specific second?

Usage
-----
    from agent import VideoQAAgent

    agent = VideoQAAgent()
    await agent.transcribe("meeting.mp4")
    answer = await agent.ask("Where was M3 discussed?")
    print(answer)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_EXAMPLE_DIR = Path(__file__).parent
_DEMOS_DIR   = _EXAMPLE_DIR.parent

_SYSTEM = """\
# Video Q&A

You are a video Q&A assistant. You answer questions about the content of a transcribed video, always citing exact timestamps so the user can jump to the source.

## Tools available

| Tool | When to use |
|---|---|
| `search_transcript` | For any content question — retrieves relevant segments with timestamps |
| `get_segment_at_time` | When the user asks what was said at a specific time |

## Answering questions

For every content question:
1. Call `search_transcript` with a focused query
2. Read the returned segments — each has `start_fmt` (e.g. "00:10:02") and `end_fmt`
3. Compose your answer, quoting or paraphrasing the relevant content
4. **Always** cite the timestamp(s) at the end: "→ discussed at **10:02**"

If multiple segments are relevant, list all timestamps.

## Timestamp format

- Use `MM:SS` for videos under an hour: `10:02`
- Use `H:MM:SS` for videos over an hour: `1:10:02`
- Always bold the timestamp: **10:02**

## Location questions

When the user asks "where", "when", or "at what point" something was discussed:
- Search for the topic
- Lead with the timestamp, then summarise what was said
- Example: "M3 was discussed at **10:02 – 11:45**. The speaker introduced..."

## No answer found

If `search_transcript` returns no relevant results, say:
"I didn't find any discussion of [topic] in the transcript. The video may not cover it."

Never guess or hallucinate content that isn't in the retrieved segments.

## Multiple related questions

If the user asks a broad question ("summarise the key points"), call `search_transcript` 2–3 times with different focused queries, then synthesise the results into a structured answer with timestamps for each point.
"""

for _p in [str(_EXAMPLE_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# LangChain tools
# ---------------------------------------------------------------------------

def _make_tools(video_path_ref: dict):
    """
    Build the three tools. transcribe_video is fast because run.py pre-warms
    the Whisper cache before invoking the agent — the tool just loads from
    disk and indexes into ChromaDB, which completes within the 30s executor
    timeout. The slow Whisper work never runs inside the agent.
    """
    from langchain_core.tools import tool
    import transcriber as tr
    import index as idx

    @tool
    def transcribe_audio(audio_path: str, model_size: str = "base") -> dict:
        """
        Load a pre-transcribed audio file into the Q&A index.

        The Whisper transcription is cached on disk. This tool loads that
        cache and indexes the segments for search — it completes in seconds.

        Args:
            audio_path: Absolute path to the audio file (.wav .mp3 .m4a .flac .ogg .aac).
            model_size: Whisper model size used during transcription.

        Returns:
            Dict with segments_count, duration_fmt, audio_path.
        """
        segments = tr.transcribe(audio_path, model_size=model_size)
        idx.index_segments(audio_path, segments)
        video_path_ref["path"]     = audio_path
        video_path_ref["segments"] = segments
        duration = segments[-1]["end"] if segments else 0
        return {
            "segments_count": len(segments),
            "duration_fmt":   tr.fmt_time(duration),
            "audio_path":     audio_path,
        }

    @tool
    def search_transcript(query: str, n_results: int = 6) -> list | dict:
        """
        Semantic search over the indexed transcript.

        Args:
            query:     Natural language query.
            n_results: Max number of segments to return (default 6).

        Returns:
            List of matching segments with text, start_fmt, end_fmt, distance.
        """
        path = video_path_ref.get("path")
        if not path:
            return {"error": "No video indexed. Call agent.transcribe() first."}
        return idx.search(path, query, n_results=n_results)

    @tool
    def get_segment_at_time(seconds: float) -> dict:
        """
        Return the transcript segment that covers a given timestamp.

        Args:
            seconds: Time offset in seconds from the start of the video.

        Returns:
            Dict with text, start_fmt, end_fmt for that moment.
        """
        segments = video_path_ref.get("segments", [])
        if not segments:
            return {"error": "No transcript loaded. Call agent.transcribe() first."}
        import index as idx
        seg = idx.get_at_time(video_path_ref.get("path", ""), seconds, segments)
        return seg if seg else {"error": "No segment found."}

    return [transcribe_audio, search_transcript, get_segment_at_time]


# ---------------------------------------------------------------------------
# VideoQAAgent — high-level wrapper
# ---------------------------------------------------------------------------

class VideoQAAgent:
    """
    High-level wrapper around CugaAgent for video Q&A.

    Manages a shared video_path_ref so all three tools operate on the
    same video after transcription.
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        whisper_model: str = "base",
    ):
        self._provider     = provider
        self._model        = model
        self._whisper_model = whisper_model
        self._video_path_ref: dict = {}
        self._agent = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def video_path(self) -> str | None:
        return self._video_path_ref.get("path")

    @property
    def segments(self) -> list[dict]:
        return self._video_path_ref.get("segments", [])

    # ------------------------------------------------------------------
    # Agent lazy-init
    # ------------------------------------------------------------------

    def _get_agent(self):
        if self._agent is None:
            from cuga import CugaAgent
            from _llm import create_llm
            llm = create_llm(provider=self._provider, model=self._model)

            self._agent = CugaAgent(
                model=llm,
                tools=_make_tools(self._video_path_ref),
                special_instructions=_SYSTEM,
                cuga_folder=str(_EXAMPLE_DIR / ".cuga"),
            )
            log.info("VideoQAAgent CugaAgent ready")
        return self._agent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask(self, question: str, thread_id: str = "video-qa") -> str:
        """
        Ask a question about the indexed video.

        Args:
            question:  Natural language question.
            thread_id: Thread for multi-turn context.

        Returns:
            Agent's answer string with timestamps.
        """
        agent = self._get_agent()
        result = await agent.invoke(question, thread_id=thread_id)
        return result.answer
