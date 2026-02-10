# Second — Development Guide

## Project Overview

**Second** is a local, privacy-first meeting note-taking tool for macOS. See `docs/PRD.md` for full product requirements.

**Stack**: Tauri 2 (Rust) + Svelte 5 (TypeScript) + Python sidecar (mlx-whisper, pyannote)

## Development Principles

### 1. Test-Driven Development (TDD)

All code changes MUST follow the Red-Green-Refactor cycle:

1. **Red**: Write a failing test FIRST that describes the desired behavior
2. **Green**: Write the minimum code to make the test pass
3. **Refactor**: Clean up the code while keeping tests green

**Rules:**
- Never write production code without a failing test
- Each commit should include the tests that cover the change
- Tests must be fast — mock external dependencies (LLM APIs, audio devices, file system I/O)
- Test names should describe behavior, not implementation: `test_assigns_speaker_to_word_by_max_overlap` not `test_interval_tree`
- Prefer integration tests over unit tests when testing pipeline stages

### 2. Keep It Simple

- No premature abstractions — three similar lines > one unnecessary helper
- No feature flags or configuration options unless the PRD specifically calls for them
- No over-engineering "for the future" — build what's needed now
- Prefer flat file structures over deeply nested directories

### 3. Privacy First

- NEVER transmit audio data outside the local machine
- Only transcript text may be sent to external LLM APIs
- All API keys stored locally in SQLite, never logged or committed
- Audio files stay in local storage, never in temp directories that sync to cloud

### 4. Error Handling

- Fail fast and loud during development — don't swallow errors
- User-facing errors must be clear and actionable ("No API key configured for Claude" not "Error: 401")
- Log errors with enough context to debug without reproducing

## Code Style & Tooling

### Rust (src-tauri/)

- **Formatter**: `cargo fmt` — run before every commit
- **Linter**: `cargo clippy -- -D warnings` — treat all warnings as errors
- **Tests**: `cargo test`
- **Style**: Follow standard Rust idioms. Use `Result<T, E>` for fallible operations. No `unwrap()` in production code — use `?` operator or explicit error handling.

```bash
# Check everything
cargo fmt --check && cargo clippy -- -D warnings && cargo test
```

### Python (backend/)

- **Runtime**: Python 3.11+ (required — uses `StrEnum` and other 3.11+ features)
- **Virtualenv**: All Python work MUST use the project venv at `backend/.venv`. macOS system Python is 3.9 and will NOT work.
- **Formatter + Linter**: `ruff` (replaces black + flake8 + isort — single fast tool)
- **Type Checker**: `mypy --strict`
- **Tests**: `pytest` with `pytest-asyncio` for async code
- **Style**: Type annotations on all function signatures. Docstrings on public functions only.

```bash
# Set up venv (one-time) — use any Python 3.11+
cd backend && python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Always activate venv before running Python commands
source backend/.venv/bin/activate

# Check everything
ruff check . && ruff format --check . && mypy . && pytest
```

### Svelte / TypeScript (frontend/)

- **Formatter**: `prettier`
- **Linter**: `eslint` with `eslint-plugin-svelte`
- **Type Checker**: `svelte-check`
- **Tests**: `vitest` (Vite-native, fast)
- **Style**: TypeScript strict mode. Explicit types on function params and return values.

```bash
# Check everything
npx eslint . && npx prettier --check . && npx svelte-check && npx vitest run
```

### Pre-Commit Checks

All three tool chains must pass before committing. Use a pre-commit hook or run manually:

```bash
# Full project check
./scripts/check.sh
```

## Project Structure

```
second/
├── CLAUDE.md                 # This file
├── docs/                     # Feature requests, specs, design docs
│   └── PRD.md                # Product requirements
├── summaries/                # Generated meeting summaries (by person)
│   └── <person_name>/
│       └── YYYY-MM-DD.md
├── src-tauri/                # Rust backend (Tauri 2)
│   ├── src/
│   │   ├── lib.rs            # Tauri entry point, IPC commands
│   │   ├── audio/            # Audio capture, mixing, VAD
│   │   └── sidecar/          # Python process management
│   ├── Cargo.toml
│   └── tauri.conf.json
├── src/                      # Svelte 5 frontend
│   ├── lib/
│   │   ├── components/       # Svelte components
│   │   ├── stores/           # Svelte stores (state management)
│   │   └── types/            # TypeScript type definitions
│   ├── routes/               # SvelteKit pages (if using SvelteKit)
│   └── app.html
├── backend/                  # Python sidecar
│   ├── main.py               # Entry point — stdin/stdout JSON protocol
│   ├── transcription/        # mlx-whisper integration
│   ├── diarization/          # pyannote pipeline
│   ├── speaker_id/           # Cross-meeting speaker identification
│   ├── summarization/        # LLM provider integrations
│   ├── db/                   # SQLite data access
│   ├── tests/                # pytest tests
│   ├── pyproject.toml
│   └── requirements.txt
├── scripts/                  # Build, test, dev scripts
│   └── check.sh              # Run all linters + tests
└── package.json              # Node dependencies (Svelte, Vite, etc.)
```

## IPC Protocol (Rust ↔ Python Sidecar)

JSON messages over stdin/stdout. Each message is a single JSON line terminated by `\n`.

**Rust → Python (requests):**
```json
{"type": "transcribe_chunk", "audio_base64": "...", "initial_prompt": "Alice Bob sprint review"}
{"type": "diarize", "audio_path": "/path/to/recording.wav", "num_speakers": 2}
{"type": "identify_speakers", "embeddings": {"SPEAKER_00": [...], "SPEAKER_01": [...]}}
{"type": "summarize", "transcript": "...", "provider": "claude", "model": "claude-sonnet-4-5-20250929", "api_key": "..."}
```

**Python → Rust (responses):**
```json
{"type": "transcription", "text": "...", "is_partial": true}
{"type": "diarization_complete", "segments": [...], "embeddings": {...}}
{"type": "speaker_match", "matches": {"SPEAKER_00": {"name": "Alice", "confidence": 0.82}}}
{"type": "summary_complete", "markdown": "..."}
{"type": "error", "message": "..."}
```

## Testing Strategy

### Unit Tests
- **Python**: Test each pipeline stage in isolation (transcription, diarization, speaker ID, summarization)
- **Rust**: Test audio mixing, VAD integration, IPC message parsing
- **Svelte**: Test component rendering, store logic, user interactions

### Integration Tests
- **Pipeline**: Feed a known audio file → verify transcript + diarization + speaker assignment output
- **IPC**: Verify Rust-Python JSON message round-trip
- **E2E**: (Future) Automated UI tests with Playwright

### Test Data
- Keep small test audio files (<10s) in `backend/tests/fixtures/`
- Mock LLM API responses — never call real APIs in tests
- Use SQLite in-memory databases for test isolation

## Git Conventions

- **Branch naming**: `feature/<name>`, `fix/<name>`, `refactor/<name>`
- **Commit messages**: Imperative mood, concise ("Add speaker embedding storage" not "Added speaker embedding storage functionality")
- **One concern per commit**: Don't mix feature code with formatting changes
