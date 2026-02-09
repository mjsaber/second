# Second — Product Requirements Document

## Overview

**Second** is a local, privacy-first meeting note-taking tool for macOS. It captures speaker and microphone audio during meetings, transcribes in real-time, identifies speakers via diarization, and generates structured summaries. Audio never leaves the device; only transcript text is sent to external LLMs for summarization.

## Target User

Individual contributor or manager who has recurring 1:1 meetings (primarily on Lark Meeting) and wants to:
- Automatically capture and transcribe meetings
- Know who said what (speaker diarization)
- Label and track participants across meetings
- Generate per-meeting summaries as markdown files
- Browse and manage summaries organized by person

## Scope (v1)

### In Scope
- Audio capture (mic + system audio from Lark Meeting)
- Real-time transcription display (accuracy can be low, corrected during summarization)
- Speaker diarization (who spoke when)
- Cross-meeting speaker identification via voice embeddings
- Speaker labeling UI (user assigns names to detected speakers)
- LLM-powered summarization (multi-provider: Claude, Gemini, GPT)
- Markdown summary file generation
- Summary file management (browse by person, by date)

### Out of Scope (v1)
- Expectation tracking / action item tracking
- Weekly team reports
- Calendar integration
- Group meeting support (>2 speakers)
- Mobile or web version
- Audio recording playback

## Architecture

### Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Desktop shell | **Tauri 2** (Rust) | Native macOS integration, small binary, system audio access |
| Frontend | **Svelte 5** + TypeScript | Compile-time reactivity, minimal bundle, fewer runtime bugs |
| Audio capture | **ScreenCaptureKit** (via Rust/cidre) | macOS-native, captures any app's audio without extra drivers |
| Microphone | **CPAL** (Rust) | Cross-platform audio I/O |
| VAD | **Silero VAD** (ONNX) | Lightweight, reduces transcription load ~70% |
| Transcription | **mlx-whisper** (Python) | 2x faster than whisper.cpp on Apple Silicon, large-v3-turbo model |
| Diarization | **pyannote community-1** (Python) | MIT license, best open-source DER, wespeaker embeddings |
| Speaker ID | **pyannote wespeaker embeddings** | Already computed during diarization, zero extra cost |
| Summarization | **Multi-provider LLM** (Python) | Claude, Gemini, GPT via API — transcript text only |
| Storage | **SQLite** | Meetings, transcripts, speaker embeddings, settings |
| Output | **Markdown files** | Simple, portable, readable |

### System Diagram

```
┌─────────────────────────────────────────────────────┐
│  Tauri 2 (Rust)                                     │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ System Audio │  │  Microphone  │  │  Silero   │  │
│  │ (SCKit)      │  │  (CPAL)      │  │  VAD      │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
│         └────────┬─────────┘              │         │
│                  ▼                        │         │
│         ┌────────────────┐               │         │
│         │  Audio Mixer   │◄──────────────┘         │
│         │  (Ring Buffer) │                          │
│         └───────┬────────┘                          │
│                 │ IPC (audio chunks)                │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  Svelte 5 Frontend (Webview)                 │   │
│  │                                              │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │   │
│  │  │ Live     │ │ Speaker  │ │ Summary      │ │   │
│  │  │ Transcript│ │ Labels   │ │ Browser      │ │   │
│  │  └──────────┘ └──────────┘ └──────────────┘ │   │
│  └──────────────────────────────────────────────┘   │
└─────────┬───────────────────────────────────────────┘
          │ IPC (commands)
          ▼
┌─────────────────────────────────────────────────────┐
│  Python Backend (sidecar process)                   │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ mlx-whisper  │  │ pyannote     │                 │
│  │ (ASR)        │  │ (diarization │                 │
│  │              │  │  + embeddings)│                 │
│  └──────┬───────┘  └──────┬───────┘                 │
│         └────────┬─────────┘                        │
│                  ▼                                   │
│  ┌──────────────────────────────────────────────┐   │
│  │  Speaker Assignment (IntervalTree)           │   │
│  └──────────────┬───────────────────────────────┘   │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  Summarization (Claude / Gemini / GPT)       │   │
│  └──────────────┬───────────────────────────────┘   │
│                 ▼                                    │
│  ┌──────────────────────────────────────────────┐   │
│  │  SQLite + Markdown Output                    │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Inter-Process Communication

Tauri 2 runs the Svelte frontend in a webview and the Python backend as a **sidecar process**. Communication:

- **Rust ↔ Frontend**: Tauri IPC commands and events
- **Rust ↔ Python sidecar**: JSON over stdin/stdout (simple, no port management)
- **Audio flow**: Rust captures audio → VAD filters silence → buffers speech chunks → sends periodically to Python sidecar for ASR

## Features

### F1: Audio Capture

**Requirements:**
- Capture system audio from Lark Meeting via ScreenCaptureKit (Core Audio Process Tap)
- Capture microphone input via CPAL
- Mix both streams into a single audio stream for transcription
- User grants Screen Recording + Microphone permission on first launch
- Audio stays 100% local — never transmitted anywhere

**UX:**
- User clicks "Start Recording" → permission prompt if needed → recording indicator shown
- User clicks "Stop Recording" → processing begins
- Audio device selection in settings (choose which mic)

### F2: Real-Time Transcription

**Requirements:**
- Display live transcript text during recording
- Low accuracy is acceptable — serves as a "it's working" indicator
- Use mlx-whisper with large-v3-turbo model (~3GB)
- Supply `initial_prompt` with known participant names and vocabulary
- VAD (Silero) filters silence to reduce processing load

**UX:**
- Scrolling transcript view during active recording
- Text appears in near real-time (1-3 second delay acceptable)
- No speaker labels during real-time phase (added in post-processing)

### F3: Post-Meeting Diarization

**Requirements:**
- After recording stops, run pyannote community-1 on the full audio
- Produce speaker segments with timestamps
- Extract wespeaker embeddings per detected speaker
- Assign speakers to transcript words using IntervalTree overlap matching
- For 30-min meetings on M3: target <3 minutes processing time

**UX:**
- Processing indicator: "Identifying speakers..." with progress
- Result: transcript reorganized by speaker turns

### F4: Speaker Identification & Labeling

**Requirements:**
- Compare extracted speaker embeddings against stored known-speaker embeddings (cosine similarity)
- If similarity > threshold (configurable, default ~0.75): auto-assign known speaker name
- If uncertain or unknown: prompt user to label
- Store speaker embeddings in SQLite, update with new meeting data for improved accuracy
- First meeting: all speakers are unknown, user labels them
- Subsequent meetings: auto-match, user confirms or corrects

**UX:**
- After diarization, show detected speakers with audio snippets or transcript excerpts
- For unknown speakers: "Who is this?" dropdown/input to assign a name
- For auto-matched speakers: "Speaker identified as [Alice] — correct?" confirmation
- Speaker management page: list all known speakers, edit names, delete

### F5: LLM Summarization

**Requirements:**
- User must select an LLM provider and configure an API key before using summarization
- Send diarized transcript (text only, with speaker labels) to external LLM
- Support multiple providers: Claude, Gemini, GPT (user configures API keys)
- Generate structured meeting summary in markdown
- Use `initial_prompt` vocabulary for improved accuracy in summary
- No separate ASR correction step — summarization LLM handles typo correction naturally

**Summary structure:**
```markdown
# Meeting: [Alice] & [Bob] — 2026-02-08

## Participants
- Alice (Engineering Manager)
- Bob (Backend Engineer)

## Summary
[2-3 sentence overview]

## Key Discussion Points
- [Topic 1]: [Details with speaker attribution]
- [Topic 2]: [Details]

## Action Items
- [ ] [Alice]: [Action item]
- [ ] [Bob]: [Action item]

## Notes
[Additional context, decisions made, etc.]
```

**UX:**
- After diarization + labeling, user clicks "Generate Summary"
- Provider selection dropdown (Claude / Gemini / GPT)
- Summary preview before saving
- Edit summary before final save

### F6: Summary File Management

**Requirements:**
- Save summaries as .md files organized by person and date
- Directory structure (within project):
  ```
  second/summaries/
  ├── alice/
  │   ├── 2026-02-01.md
  │   ├── 2026-02-08.md
  │   └── 2026-02-15.md
  └── bob/
      ├── 2026-02-03.md
      └── 2026-02-10.md
  ```
- SQLite index for fast search and metadata queries
- Browse summaries by person or by date

**UX:**
- Sidebar: list of people with meeting count
- Click person → chronological list of meeting summaries
- Click summary → read/edit markdown
- Search across all summaries (full-text search via SQLite FTS5)

## Data Model (SQLite)

```sql
-- Known speakers with voice embeddings
CREATE TABLE speakers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    embedding BLOB,          -- averaged wespeaker embedding vector
    embedding_count INTEGER DEFAULT 0,  -- how many meetings contributed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Meeting recordings
CREATE TABLE meetings (
    id INTEGER PRIMARY KEY,
    title TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    audio_path TEXT,          -- path to local .wav file
    status TEXT DEFAULT 'recording',  -- recording | processing | completed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Meeting participants (join table)
CREATE TABLE meeting_speakers (
    meeting_id INTEGER REFERENCES meetings(id),
    speaker_id INTEGER REFERENCES speakers(id),
    diarization_label TEXT,   -- e.g., "SPEAKER_00"
    PRIMARY KEY (meeting_id, speaker_id)
);

-- Raw transcript segments with speaker assignment
CREATE TABLE transcript_segments (
    id INTEGER PRIMARY KEY,
    meeting_id INTEGER REFERENCES meetings(id),
    speaker_id INTEGER REFERENCES speakers(id),
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL
);

-- Generated summaries
CREATE TABLE summaries (
    id INTEGER PRIMARY KEY,
    meeting_id INTEGER REFERENCES meetings(id),
    provider TEXT NOT NULL,   -- claude | gemini | gpt
    model TEXT NOT NULL,      -- specific model name
    content TEXT NOT NULL,    -- markdown content
    file_path TEXT,           -- path to .md file under summaries/
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API key storage
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Full-text search on transcripts
CREATE VIRTUAL TABLE transcript_fts USING fts5(text, content=transcript_segments, content_rowid=id);

-- Full-text search on summaries
CREATE VIRTUAL TABLE summary_fts USING fts5(content, content=summaries, content_rowid=id);
```

## Processing Pipeline

```
1. User clicks "Start Recording"
   → Rust: begin audio capture (mic + system)
   → Rust: stream speech chunks to Python (after VAD)
   → Python: mlx-whisper real-time transcription
   → Frontend: display live transcript

2. User clicks "Stop Recording"
   → Rust: stop capture, save full audio to .wav
   → Python: run pyannote diarization on full audio (~2-3 min)
   → Python: extract speaker embeddings
   → Python: assign speakers to transcript via IntervalTree
   → Python: compare embeddings against known speakers

3. Speaker labeling
   → Frontend: show detected speakers with auto-match suggestions
   → User confirms/corrects labels
   → Python: update speaker embeddings in SQLite

4. Summarization
   → User clicks "Generate Summary"
   → Python: send labeled transcript to chosen LLM
   → Frontend: show summary preview
   → User edits if needed, clicks "Save"
   → Python: save .md file + index in SQLite
```

## Non-Functional Requirements

- **Privacy**: Audio never leaves the device. Only transcript text sent to LLM APIs.
- **Performance**: Real-time transcription with 1-3s delay. Post-meeting processing <3 min for 30-min recording on M3 18GB.
- **Storage**: SQLite single-file database. Markdown files in `second/summaries/` directory.
- **Audio retention**: User choice in settings, default to keep .wav files for potential reprocessing.
- **Permissions**: Screen Recording + Microphone (both required, requested on first launch).
- **macOS**: Requires macOS 14+ (Sonoma) for ScreenCaptureKit Process Tap API.
- **LLM requirement**: User must configure at least one LLM provider API key. No offline/local LLM fallback in v1.
