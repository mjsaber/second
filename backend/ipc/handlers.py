"""Handler functions for each IPC message type.

Each handler receives an IPCMessage and returns an IPCResponse.
Heavy ML dependencies are lazy-imported to keep startup fast.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ipc.protocol import IPCMessage, IPCResponse, MessageType, ResponseType

# ---------------------------------------------------------------------------
# Lazy-loaded singletons and helpers
# ---------------------------------------------------------------------------

_db_instance: Any = None
_db_instance_path: str | None = None
_transcription_engines: dict[str, Any] = {}

# Default settings values
_SETTINGS_DEFAULTS: dict[str, str] = {
    "llm_provider": "",
    "model_name": "",
    "api_key": "",
    "audio_device": "",
    "audio_retention": "keep",
}


def _get_db(db_path: str | None = None) -> Any:
    """Return a shared DatabaseManager instance (lazy-initialized).

    In production the DB path comes from an environment variable or config;
    in tests this function is patched to return an in-memory database.
    """
    global _db_instance, _db_instance_path
    if _db_instance is None:
        import os

        from db.database import DatabaseManager

        if db_path is not None and not str(db_path).strip():
            db_path = None
        if db_path is None:
            db_path = os.environ.get("SECOND_DB_PATH")
        if db_path is None:
            base_dir = os.path.join(os.path.expanduser("~"), ".second")
            os.makedirs(base_dir, exist_ok=True)
            db_path = os.path.join(base_dir, "second.db")
        _db_instance = DatabaseManager(db_path)
        _db_instance.initialize()
        _db_instance_path = db_path
    elif db_path is not None and _db_instance_path != db_path:
        import os

        from db.database import DatabaseManager

        if not str(db_path).strip():
            return _db_instance
        base_dir = os.path.dirname(db_path)
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)
        _db_instance = DatabaseManager(db_path)
        _db_instance.initialize()
        _db_instance_path = db_path
    return _db_instance


def _get_summary_dir() -> str:
    """Return the base directory for summary files.

    In tests this is patched to return a temporary directory.
    """
    import os

    return os.environ.get("SECOND_SUMMARIES_DIR", "summaries")


def _merge_diarization_with_transcript(
    diarization_segments: list[Any],
    transcript_segments: list[Any],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for diar_seg in diarization_segments:
        texts: list[str] = []
        for trans_seg in transcript_segments:
            overlap_start = max(diar_seg.start, trans_seg.start)
            overlap_end = min(diar_seg.end, trans_seg.end)
            if overlap_end > overlap_start:
                text = trans_seg.text.strip()
                if text:
                    texts.append(text)
        merged.append(
            {
                "speaker": diar_seg.speaker,
                "start": diar_seg.start,
                "end": diar_seg.end,
                "text": " ".join(texts),
            }
        )
    return merged


# ---------------------------------------------------------------------------
# Existing handlers
# ---------------------------------------------------------------------------


def handle_health(msg: IPCMessage) -> IPCResponse:
    """Handle a health check message."""
    return IPCResponse.ok(ResponseType.HEALTH, status="ok")


def handle_transcribe_chunk(msg: IPCMessage) -> IPCResponse:
    """Handle a transcribe_chunk message.

    Base64-decodes the audio payload, runs it through TranscriptionEngine,
    and returns the transcription result.

    Required payload fields: audio_base64.
    Optional payload fields: initial_prompt, language.
    """
    if "audio_base64" not in msg.payload:
        return IPCResponse.error(
            "Missing required field 'audio_base64' in transcribe_chunk message"
        )

    import base64

    audio_bytes = base64.b64decode(msg.payload["audio_base64"])
    initial_prompt: str = msg.payload.get("initial_prompt", "")
    language: str | None = msg.payload.get("language")

    try:
        from transcription.engine import TranscriptionEngine

        # Reuse engine per language to avoid reloading the model each call
        cache_key = language or "_auto"
        if cache_key not in _transcription_engines:
            engine = TranscriptionEngine(language=language)
            engine.load_model()
            _transcription_engines[cache_key] = engine
        engine = _transcription_engines[cache_key]
        segments = engine.transcribe(audio_bytes, initial_prompt=initial_prompt)

        full_text = "".join(seg.text for seg in segments).strip()
        is_partial = segments[-1].is_partial if segments else False

        segments_data = [
            {
                "text": seg.text,
                "start": seg.start,
                "end": seg.end,
                "is_partial": seg.is_partial,
            }
            for seg in segments
        ]

        return IPCResponse.ok(
            ResponseType.TRANSCRIPTION,
            text=full_text,
            segments=segments_data,
            is_partial=is_partial,
        )
    except (RuntimeError, ValueError) as exc:
        return IPCResponse.error(str(exc))


def handle_diarize(msg: IPCMessage) -> IPCResponse:
    """Handle a diarize message.

    Runs the pyannote diarization pipeline on the given audio file and returns
    speaker segments with per-speaker embeddings.

    Required payload fields: audio_path.
    Optional payload fields: num_speakers.
    """
    if "audio_path" not in msg.payload:
        return IPCResponse.error("Missing required field 'audio_path' in diarize message")

    audio_path: str = msg.payload["audio_path"]
    # Validate audio file has a recognized extension
    valid_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    from pathlib import Path as _Path

    if _Path(audio_path).suffix.lower() not in valid_extensions:
        return IPCResponse.error(
            f"Invalid audio file extension: {_Path(audio_path).suffix!r}. "
            f"Expected one of: {', '.join(sorted(valid_extensions))}"
        )
    num_speakers: int | None = msg.payload.get("num_speakers")

    try:
        from diarization.pipeline import DiarizationPipeline
        from transcription.engine import TranscriptionEngine

        pipeline = DiarizationPipeline()
        pipeline.load()
        result = pipeline.diarize(audio_path, num_speakers=num_speakers)
        embeddings = pipeline.extract_embeddings(audio_path, result.segments)

        cache_key = "_file"
        if cache_key not in _transcription_engines:
            engine = TranscriptionEngine()
            engine.load_model()
            _transcription_engines[cache_key] = engine
        engine = _transcription_engines[cache_key]
        transcript_segments = engine.transcribe_file(audio_path)

        segments_data = _merge_diarization_with_transcript(result.segments, transcript_segments)

        return IPCResponse.ok(
            ResponseType.DIARIZATION_COMPLETE,
            segments=segments_data,
            embeddings=embeddings,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        return IPCResponse.error(str(exc))


def handle_identify_speakers(msg: IPCMessage) -> IPCResponse:
    """Handle an identify_speakers message.

    Required payload fields: embeddings.
    Optional payload fields: known_embeddings, db_path.

    When db_path is provided (or a DB is available), the handler:
    - Loads known embeddings from the speakers table
    - For matched speakers: updates their embeddings via running average
    - For unmatched speakers: creates new speaker records with their embeddings
    """
    if "embeddings" not in msg.payload:
        return IPCResponse.error("Missing required field 'embeddings' in identify_speakers message")

    from speaker_id.identifier import SpeakerIdentifier

    embeddings: dict[str, list[float]] = msg.payload["embeddings"]
    known_embeddings: dict[str, list[float]] | None = msg.payload.get("known_embeddings")
    db_path = msg.payload.get("db_path")
    has_db = db_path is not None

    if has_db:
        db = _get_db(str(db_path))
        identifier = SpeakerIdentifier(db=db)
        matches = identifier.identify_from_db(embeddings)

        # Persist: update matched, create unmatched
        for speaker_match in matches:
            label = speaker_match.speaker_label
            embedding = embeddings[label]

            if speaker_match.matched_name is not None:
                # Update existing speaker's embedding
                speaker_row = db.get_speaker_by_name(speaker_match.matched_name)
                if speaker_row is not None:
                    identifier.update_speaker_embedding(speaker_row["id"], embedding)
            else:
                # Create new speaker record
                new_id = db.create_speaker(label)
                blob = SpeakerIdentifier.serialize_embedding(embedding)
                db.update_speaker_embedding(new_id, blob, 1)
    else:
        identifier = SpeakerIdentifier()
        matches = identifier.identify(embeddings, known_embeddings=known_embeddings)

    matches_data = [
        {
            "speaker_label": m.speaker_label,
            "matched_name": m.matched_name,
            "confidence": m.confidence,
        }
        for m in matches
    ]

    return IPCResponse.ok(ResponseType.SPEAKER_MATCH, matches=matches_data)


def handle_create_meeting(msg: IPCMessage) -> IPCResponse:
    title: str | None = msg.payload.get("title")
    audio_path: str | None = msg.payload.get("audio_path")
    db = _get_db()
    meeting_id = db.create_meeting(title=title, audio_path=audio_path)
    return IPCResponse.ok(ResponseType.MEETING_CREATED, meeting_id=meeting_id)


def handle_summarize(msg: IPCMessage) -> IPCResponse:
    """Handle a summarize message.

    Required payload fields: transcript, provider, model, api_key.
    """
    required_fields = ("transcript", "provider", "model", "api_key")
    for field in required_fields:
        if field not in msg.payload:
            return IPCResponse.error(f"Missing required field '{field}' in summarize message")

    from summarization.providers import (
        LLMProvider,
        SummarizationRequest,
        SummarizationService,
    )

    service = SummarizationService()
    request = SummarizationRequest(
        transcript=msg.payload["transcript"],
        provider=LLMProvider(msg.payload["provider"]),
        model=msg.payload["model"],
        api_key=msg.payload["api_key"],
    )

    try:
        result = service.summarize(request)
    except (ValueError, ConnectionError, RuntimeError) as e:
        return IPCResponse.error(str(e))

    return IPCResponse.ok(
        ResponseType.SUMMARY_COMPLETE,
        markdown=result.markdown,
        provider=result.provider.value,
        model=result.model,
        token_count=result.token_count,
    )


# ---------------------------------------------------------------------------
# New handlers
# ---------------------------------------------------------------------------


def handle_save_summary(msg: IPCMessage) -> IPCResponse:
    """Handle a save_summary message.

    Writes the markdown summary to disk via SummaryFileManager and inserts
    a record into the summaries table.

    Required payload fields: meeting_id, provider, model, content,
                             speaker_names, date.
    """
    required_fields = ("meeting_id", "provider", "model", "content", "speaker_names", "date")
    for field in required_fields:
        if field not in msg.payload:
            return IPCResponse.error(f"Missing required field '{field}' in save_summary message")

    from summaries.file_manager import SummaryFileManager

    meeting_id: int = msg.payload["meeting_id"]
    provider: str = msg.payload["provider"]
    model: str = msg.payload["model"]
    content: str = msg.payload["content"]
    speaker_names: list[str] = msg.payload["speaker_names"]
    date: str = msg.payload["date"]

    db = _get_db()
    summary_dir = _get_summary_dir()
    file_manager = SummaryFileManager(summary_dir)

    # Write a file per speaker (or use the first speaker as the primary)
    speaker_name = speaker_names[0] if speaker_names else "unknown"
    file_path = file_manager.save_summary(speaker_name, date, content)

    summary_id = db.create_summary(
        meeting_id=meeting_id,
        provider=provider,
        model=model,
        content=content,
        file_path=str(file_path),
    )

    return IPCResponse.ok(
        ResponseType.SUMMARY_SAVED,
        summary_id=summary_id,
        file_path=str(file_path),
    )


def handle_get_all_speakers(msg: IPCMessage) -> IPCResponse:
    """Handle a get_all_speakers message.

    Returns all speakers with their meeting counts.
    """
    db = _get_db()
    speakers = db.get_all_speakers()

    speakers_data: list[dict[str, Any]] = []
    for speaker in speakers:
        # Count meetings for this speaker
        meeting_count = db.connection.execute(
            "SELECT COUNT(*) as cnt FROM meeting_speakers WHERE speaker_id = ?",
            (speaker["id"],),
        ).fetchone()["cnt"]

        speakers_data.append(
            {
                "id": speaker["id"],
                "name": speaker["name"],
                "meeting_count": meeting_count,
            }
        )

    return IPCResponse.ok(ResponseType.SPEAKERS_LIST, speakers=speakers_data)


def handle_get_summaries_for_speaker(msg: IPCMessage) -> IPCResponse:
    """Handle a get_summaries_for_speaker message.

    Required payload fields: speaker_name.
    """
    if "speaker_name" not in msg.payload:
        return IPCResponse.error(
            "Missing required field 'speaker_name' in get_summaries_for_speaker message"
        )

    speaker_name: str = msg.payload["speaker_name"]
    db = _get_db()

    # Find the speaker
    speaker = db.get_speaker_by_name(speaker_name)
    if speaker is None:
        return IPCResponse.ok(ResponseType.SUMMARIES_LIST, summaries=[])

    # Get meetings for this speaker, then summaries for those meetings
    meeting_rows = db.connection.execute(
        "SELECT meeting_id FROM meeting_speakers WHERE speaker_id = ?",
        (speaker["id"],),
    ).fetchall()
    meeting_ids = [row["meeting_id"] for row in meeting_rows]

    if not meeting_ids:
        return IPCResponse.ok(ResponseType.SUMMARIES_LIST, summaries=[])

    placeholders = ",".join("?" * len(meeting_ids))
    summary_rows = db.connection.execute(
        f"SELECT * FROM summaries WHERE meeting_id IN ({placeholders})",
        meeting_ids,
    ).fetchall()

    summaries_data = [
        {
            "id": row["id"],
            "meeting_id": row["meeting_id"],
            "date": row["created_at"],
            "preview_text": row["content"][:200] if row["content"] else "",
            "provider": row["provider"],
            "model": row["model"],
        }
        for row in summary_rows
    ]

    return IPCResponse.ok(ResponseType.SUMMARIES_LIST, summaries=summaries_data)


def handle_get_summary_detail(msg: IPCMessage) -> IPCResponse:
    """Handle a get_summary_detail message.

    Required payload fields: summary_id.
    """
    if "summary_id" not in msg.payload:
        return IPCResponse.error(
            "Missing required field 'summary_id' in get_summary_detail message"
        )

    summary_id: int = msg.payload["summary_id"]
    db = _get_db()

    row = db.connection.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)).fetchone()

    if row is None:
        return IPCResponse.error(f"Summary not found for id={summary_id}")

    return IPCResponse.ok(
        ResponseType.SUMMARY_DETAIL,
        id=row["id"],
        meeting_id=row["meeting_id"],
        content=row["content"],
        provider=row["provider"],
        model=row["model"],
        created_at=row["created_at"],
        file_path=row["file_path"],
    )


def handle_search_summaries(msg: IPCMessage) -> IPCResponse:
    """Handle a search_summaries message.

    Required payload fields: query.
    Uses FTS5 full-text search via DatabaseManager.search_summaries().
    """
    if "query" not in msg.payload:
        return IPCResponse.error("Missing required field 'query' in search_summaries message")

    query: str = msg.payload["query"]
    db = _get_db()

    rows = db.search_summaries(query)

    results_data = [
        {
            "id": row["id"],
            "meeting_id": row["meeting_id"],
            "content": row["content"],
            "provider": row["provider"],
            "model": row["model"],
            "created_at": row["created_at"],
            "file_path": row["file_path"],
        }
        for row in rows
    ]

    return IPCResponse.ok(ResponseType.SEARCH_RESULTS, results=results_data)


def handle_save_settings(msg: IPCMessage) -> IPCResponse:
    """Handle a save_settings message.

    Required payload fields: settings (dict).
    Persists each key-value pair to the settings table.
    """
    if "settings" not in msg.payload:
        return IPCResponse.error("Missing required field 'settings' in save_settings message")

    settings: dict[str, str] = msg.payload["settings"]
    db = _get_db()

    for key, value in settings.items():
        db.set_setting(key, str(value))

    return IPCResponse.ok(ResponseType.SETTINGS_SAVED, success=True)


def handle_load_settings(msg: IPCMessage) -> IPCResponse:
    """Handle a load_settings message.

    Loads all settings from the DB and merges with defaults.
    """
    db = _get_db()

    settings: dict[str, str] = {}
    for key, default_value in _SETTINGS_DEFAULTS.items():
        stored = db.get_setting(key)
        settings[key] = stored if stored is not None else default_value
    if settings.get("audio_retention") not in {"keep", "delete"}:
        settings["audio_retention"] = _SETTINGS_DEFAULTS["audio_retention"]

    return IPCResponse.ok(ResponseType.SETTINGS_LOADED, settings=settings)


# ---------------------------------------------------------------------------
# Handler map
# ---------------------------------------------------------------------------

HANDLER_MAP: dict[str, Callable[[IPCMessage], IPCResponse]] = {
    MessageType.HEALTH: handle_health,
    MessageType.TRANSCRIBE_CHUNK: handle_transcribe_chunk,
    MessageType.DIARIZE: handle_diarize,
    MessageType.CREATE_MEETING: handle_create_meeting,
    MessageType.IDENTIFY_SPEAKERS: handle_identify_speakers,
    MessageType.SUMMARIZE: handle_summarize,
    MessageType.SAVE_SUMMARY: handle_save_summary,
    MessageType.GET_ALL_SPEAKERS: handle_get_all_speakers,
    MessageType.GET_SUMMARIES_FOR_SPEAKER: handle_get_summaries_for_speaker,
    MessageType.GET_SUMMARY_DETAIL: handle_get_summary_detail,
    MessageType.SEARCH_SUMMARIES: handle_search_summaries,
    MessageType.SAVE_SETTINGS: handle_save_settings,
    MessageType.LOAD_SETTINGS: handle_load_settings,
}
