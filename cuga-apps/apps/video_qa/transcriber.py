"""
Transcriber — transcribe audio files with Whisper.

Returns timestamped segments: [{text, start, end, start_fmt, end_fmt}, ...]

Supported formats: .wav  .mp3  .m4a  .flac  .ogg  .aac
No ffmpeg required — audio files are fed directly to Whisper.

Dependencies (install once):
    pip install faster-whisper

faster-whisper is ~4x faster than openai-whisper and returns word-level timestamps.
Falls back to openai-whisper if faster-whisper is not installed.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}

_CACHE_DIR = Path(__file__).parent / ".cache" / "transcripts"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def transcribe(audio_path: str | Path, model_size: str = "base") -> list[dict[str, Any]]:
    """
    Transcribe an audio file and return timestamped segments.

    Each segment: {text, start, end, start_fmt, end_fmt}
    Results are cached on disk by file hash.

    Args:
        audio_path: Path to .wav, .mp3, .m4a, .flac, .ogg, or .aac file.
        model_size: Whisper model size — "tiny", "base", "small", "medium", "large-v3".
    """
    audio_path = Path(audio_path)

    if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(
            f"Unsupported format '{audio_path.suffix}'. "
            f"Only audio files are supported: {', '.join(sorted(AUDIO_EXTENSIONS))}. "
            f"For video files, extract the audio first with: "
            f"ffmpeg -i input.mp4 -vn -acodec pcm_s16le output.wav"
        )

    # In Docker, audio files must be placed in apps/video_qa/videos/ on the host,
    # which is mounted read-only at /audio inside the container.
    _audio_dir = Path("/audio")
    if _audio_dir.exists():
        try:
            audio_path.resolve().relative_to(_audio_dir.resolve())
        except ValueError:
            raise ValueError(
                f"Running in Docker — files must be inside /audio. "
                f"Copy your file to apps/video_qa/videos/ on the host and use "
                f"/audio/<filename> as the path. Got: {audio_path}"
            )

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    cache_key  = _file_hash(audio_path)
    cache_file = _CACHE_DIR / f"{cache_key}_{model_size}.json"

    if cache_file.exists():
        log.info("Transcript cache hit: %s", cache_file.name)
        return json.loads(cache_file.read_text())

    log.info("Transcribing %s with model=%s", audio_path.name, model_size)
    segments = _run_whisper(audio_path, model_size)
    cache_file.write_text(json.dumps(segments, ensure_ascii=False, indent=2))
    log.info("Transcription complete — %d segments, cached at %s", len(segments), cache_file.name)
    return segments


def invalidate_cache(audio_path: str | Path, model_size: str = "base") -> None:
    audio_path = Path(audio_path)
    cache_key  = _file_hash(audio_path)
    cache_file = _CACHE_DIR / f"{cache_key}_{model_size}.json"
    if cache_file.exists():
        cache_file.unlink()
        log.info("Cache invalidated: %s", cache_file.name)


def fmt_time(seconds: float) -> str:
    """Format seconds as H:MM:SS (or MM:SS if under one hour)."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    with path.open("rb") as f:
        h.update(f.read(1024 * 1024))
    return h.hexdigest()[:16]


def _run_whisper(audio_path: Path, model_size: str) -> list[dict[str, Any]]:
    try:
        return _faster_whisper(audio_path, model_size)
    except ImportError:
        log.warning("faster-whisper not installed — trying openai-whisper")
    return _openai_whisper(audio_path, model_size)


def _faster_whisper(audio_path: Path, model_size: str) -> list[dict[str, Any]]:
    from faster_whisper import WhisperModel

    # cpu_threads=2 leaves CPUs free for uvicorn to stay responsive during transcription.
    model = WhisperModel(model_size, compute_type="int8", cpu_threads=2, num_workers=1)
    log.info("Running faster-whisper (%s)…", model_size)

    segments_iter, _ = model.transcribe(
        str(audio_path), beam_size=5, vad_filter=True, word_timestamps=False,
    )

    segments = []
    for seg in segments_iter:
        segments.append({
            "text":      seg.text.strip(),
            "start":     round(seg.start, 2),
            "end":       round(seg.end, 2),
            "start_fmt": fmt_time(seg.start),
            "end_fmt":   fmt_time(seg.end),
        })
    return segments


def _openai_whisper(audio_path: Path, model_size: str) -> list[dict[str, Any]]:
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "No Whisper library found. Install one of:\n"
            "  pip install faster-whisper   (recommended)\n"
            "  pip install openai-whisper"
        )

    log.info("Running openai-whisper (%s)…", model_size)
    model  = whisper.load_model(model_size)
    result = model.transcribe(str(audio_path), verbose=False)

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "text":      seg["text"].strip(),
            "start":     round(seg["start"], 2),
            "end":       round(seg["end"], 2),
            "start_fmt": fmt_time(seg["start"]),
            "end_fmt":   fmt_time(seg["end"]),
        })
    return segments
