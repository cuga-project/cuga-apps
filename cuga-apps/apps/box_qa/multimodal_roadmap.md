# Box Q&A → Multimodal Roadmap

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER ASKS A QUESTION                            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   list_box_folder /    │
                    │   search_box (tool)    │
                    └────────────┬───────────┘
                                 │
                    ┌────────────▼───────────┐
                    │   File type detected   │
                    └──┬──────────┬──────────┘
                       │          │
           ────────────┘          └────────────
          │                                    │
          ▼                                    ▼
 ┌─────────────────┐                 ┌──────────────────┐
 │  DOCUMENT       │                 │  VIDEO / AUDIO   │
 │  PDF, DOCX,     │                 │  MP4, MOV,       │
 │  PPTX, TXT …    │                 │  MP3, WAV …      │
 └────────┬────────┘                 └────────┬─────────┘
          │                                   │
          ▼                                   │
 ┌─────────────────┐          ┌──────────────▼──────────────────────┐
 │ get_file_content│          │           (v1 — NOT SUPPORTED)      │
 │  • TXT/MD: read │          │  Return: "media file, cannot read"  │
 │  • PDF/Office:  │          └──────────────┬──────────────────────┘
 │    docling OCR  │                         │
 └────────┬────────┘             ┌───────────▼──── V2 ADDITIONS ───────────────────┐
          │                      │                                                  │
          │                      │  ┌──────────────────────────────┐               │
          │                      │  │   get_media_transcript tool  │               │
          │                      │  │                              │               │
          │                      │  │  1. Download file from Box   │               │
          │                      │  │  2. Extract audio (ffmpeg)   │               │
          │                      │  │  3. Run Whisper / STT API    │               │
          │                      │  │  4. Cache timestamped        │               │
          │                      │  │     transcript (.json)       │               │
          │                      │  └──────────────┬───────────────┘               │
          │                      │                 │                               │
          │                      │  ┌──────────────▼───────────────┐               │
          │                      │  │  (optional) Vision tool      │               │
          │                      │  │  for video keyframes         │               │
          │                      │  │                              │               │
          │                      │  │  1. Extract frames (ffmpeg)  │               │
          │                      │  │  2. Send to vision LLM       │               │
          │                      │  │     (Claude / GPT-4o)        │               │
          │                      │  │  3. Add visual descriptions  │               │
          │                      │  │     to transcript            │               │
          │                      │  └──────────────┬───────────────┘               │
          │                      └───────────────────────────────────────────────── ┘
          │                                        │
          └──────────────────┬─────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   CugaAgent reasons      │
              │   across all content     │
              │   (docs + transcripts)   │
              └──────────────┬───────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   Answer with citations  │
              │                          │
              │  [doc.pdf] — "quote"     │
              │  [video.mp4] at 02:14 —  │
              │  "transcript segment"    │
              └──────────────────────────┘
```

## What changes between v1 → v2

| Concern          | v1 (now)                    | v2 (multimodal)                          |
|------------------|-----------------------------|------------------------------------------|
| File types       | PDF, DOCX, TXT, CSV, …      | + MP4, MOV, MP3, WAV, …                 |
| New tool         | —                           | `get_media_transcript(file_id)`          |
| Audio extraction | —                           | `ffmpeg` strips audio track              |
| Transcription    | —                           | `faster-whisper` (local) or Whisper API  |
| Keyframe vision  | —                           | optional: `ffmpeg` + vision LLM          |
| Caching          | docling result cached       | transcript JSON cached alongside docs    |
| Citations        | `[filename]` — "quote"      | `[filename]` at `MM:SS` — "segment"     |
| New dependencies | —                           | `faster-whisper`, `ffmpeg`, vision model |

## Key insight for the multimodal pitch

Box is an enterprise file store. Real enterprise folders are mixed:
- Sales decks (PPTX) alongside demo recordings (MP4)
- Written reports (PDF) alongside town hall recordings (MP3)
- Contracts (DOCX) alongside explainer videos (MOV)

A Q&A agent that silently skips half the folder is incomplete.
The multimodal version lets a user ask:

> "What did the CEO say about the Q4 roadmap?" 

…and get an answer whether that content lives in a slide deck, a PDF memo,
or a recorded all-hands — with citations across all three.
```
