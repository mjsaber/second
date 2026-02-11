"""Extended tests for IPC handler functions.

Tests for: handle_transcribe_chunk (wired), handle_diarize (embeddings),
handle_identify_speakers (DB persistence), save_summary, get_all_speakers,
get_summaries_for_speaker, get_summary_detail, search_summaries,
save_settings, load_settings.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db.database import DatabaseManager
from ipc import handlers as _handlers_module
from ipc.protocol import IPCMessage, IPCResponse, MessageType, ResponseType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_engine_cache() -> None:
    """Clear the transcription engine cache between tests for mock isolation."""
    _handlers_module._transcription_engines.clear()


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    """Provide a fresh in-memory DB for each test."""
    db = DatabaseManager(db_path=None)
    db.initialize()
    yield db  # type: ignore[misc]
    db.close()


@pytest.fixture
def tmp_summaries_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for summary files."""
    d = tmp_path / "summaries"
    d.mkdir()
    return d


# ===========================================================================
# 1. handle_transcribe_chunk — wired to TranscriptionEngine
# ===========================================================================


class TestHandleTranscribeChunkWired:
    """Tests for the wired transcribe_chunk handler (using TranscriptionEngine)."""

    def test_returns_transcription_from_engine(self) -> None:
        """Verify the handler calls the engine and returns actual text."""
        from ipc.handlers import handle_transcribe_chunk

        mock_engine_cls = MagicMock()
        mock_engine_inst = MagicMock()
        mock_segment = MagicMock(text="Hello world", start=0.0, end=1.5, is_partial=False)
        mock_engine_inst.transcribe.return_value = [mock_segment]
        mock_engine_cls.return_value = mock_engine_inst

        audio_bytes = b"\x00\x01" * 100
        audio_b64 = base64.b64encode(audio_bytes).decode()

        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": audio_b64},
        )
        with patch("transcription.engine.TranscriptionEngine", mock_engine_cls):
            resp = handle_transcribe_chunk(msg)

        assert resp.type == ResponseType.TRANSCRIPTION
        assert resp.data["text"] == "Hello world"
        assert len(resp.data["segments"]) == 1
        assert resp.data["segments"][0]["text"] == "Hello world"

    def test_passes_initial_prompt_to_engine(self) -> None:
        """Verify the handler forwards initial_prompt to the engine."""
        from ipc.handlers import handle_transcribe_chunk

        mock_engine_cls = MagicMock()
        mock_engine_inst = MagicMock()
        mock_engine_inst.transcribe.return_value = []
        mock_engine_cls.return_value = mock_engine_inst

        audio_bytes = b"\x00\x01" * 100
        audio_b64 = base64.b64encode(audio_bytes).decode()

        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": audio_b64, "initial_prompt": "Alice Bob sprint"},
        )
        with patch("transcription.engine.TranscriptionEngine", mock_engine_cls):
            handle_transcribe_chunk(msg)

        mock_engine_inst.transcribe.assert_called_once()
        call_kwargs = mock_engine_inst.transcribe.call_args
        assert call_kwargs[1].get("initial_prompt") == "Alice Bob sprint" or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "Alice Bob sprint"
        )

    def test_returns_empty_text_for_silence(self) -> None:
        """Verify the handler returns empty text when engine returns no segments."""
        from ipc.handlers import handle_transcribe_chunk

        mock_engine_cls = MagicMock()
        mock_engine_inst = MagicMock()
        mock_engine_inst.transcribe.return_value = []
        mock_engine_cls.return_value = mock_engine_inst

        audio_bytes = b"\x00" * 100
        audio_b64 = base64.b64encode(audio_bytes).decode()

        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": audio_b64},
        )
        with patch("transcription.engine.TranscriptionEngine", mock_engine_cls):
            resp = handle_transcribe_chunk(msg)

        assert resp.type == ResponseType.TRANSCRIPTION
        assert resp.data["text"] == ""
        assert resp.data["segments"] == []

    def test_returns_error_on_engine_failure(self) -> None:
        """Verify the handler returns an error if the engine raises."""
        from ipc.handlers import handle_transcribe_chunk

        mock_engine_cls = MagicMock()
        mock_engine_inst = MagicMock()
        mock_engine_inst.transcribe.side_effect = RuntimeError("Model not loaded")
        mock_engine_cls.return_value = mock_engine_inst

        audio_bytes = b"\x00\x01" * 100
        audio_b64 = base64.b64encode(audio_bytes).decode()

        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": audio_b64},
        )
        with patch("transcription.engine.TranscriptionEngine", mock_engine_cls):
            resp = handle_transcribe_chunk(msg)

        assert resp.type == ResponseType.ERROR
        assert "Model not loaded" in resp.data["message"]

    def test_returns_is_partial_from_segments(self) -> None:
        """Verify is_partial is taken from the last segment."""
        from ipc.handlers import handle_transcribe_chunk

        mock_engine_cls = MagicMock()
        mock_engine_inst = MagicMock()
        seg1 = MagicMock(text="Hello", start=0.0, end=0.5, is_partial=False)
        seg2 = MagicMock(text="world", start=0.5, end=1.0, is_partial=True)
        mock_engine_inst.transcribe.return_value = [seg1, seg2]
        mock_engine_cls.return_value = mock_engine_inst

        audio_b64 = base64.b64encode(b"\x00" * 100).decode()
        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": audio_b64},
        )
        with patch("transcription.engine.TranscriptionEngine", mock_engine_cls):
            resp = handle_transcribe_chunk(msg)

        assert resp.data["is_partial"] is True


# ===========================================================================
# 2. handle_diarize — embedding extraction
# ===========================================================================


class TestHandleDiarizeEmbeddings:
    """Tests that handle_diarize returns embeddings from the pipeline."""

    def test_returns_embeddings_alongside_segments(self) -> None:
        """Verify embeddings dict is included in the response."""
        from ipc.handlers import handle_diarize

        mock_pipeline_cls = MagicMock()
        mock_pipeline_inst = MagicMock()
        seg = MagicMock(speaker="SPEAKER_00", start=0.0, end=5.0)
        mock_pipeline_inst.diarize.return_value = MagicMock(segments=[seg])
        mock_pipeline_inst.extract_embeddings.return_value = {
            "SPEAKER_00": [0.1, 0.2, 0.3]
        }
        mock_pipeline_cls.return_value = mock_pipeline_inst

        msg = IPCMessage(
            type=MessageType.DIARIZE,
            payload={"audio_path": "/tmp/test.wav"},
        )
        with patch("diarization.pipeline.DiarizationPipeline", mock_pipeline_cls):
            resp = handle_diarize(msg)

        assert resp.type == ResponseType.DIARIZATION_COMPLETE
        assert resp.data["embeddings"] == {"SPEAKER_00": [0.1, 0.2, 0.3]}
        assert len(resp.data["segments"]) == 1

    def test_calls_extract_embeddings_with_segments(self) -> None:
        """Verify extract_embeddings is called with audio_path and segments."""
        from ipc.handlers import handle_diarize

        mock_pipeline_cls = MagicMock()
        mock_pipeline_inst = MagicMock()
        seg = MagicMock(speaker="SPEAKER_00", start=0.0, end=5.0)
        result = MagicMock(segments=[seg])
        mock_pipeline_inst.diarize.return_value = result
        mock_pipeline_inst.extract_embeddings.return_value = {}
        mock_pipeline_cls.return_value = mock_pipeline_inst

        msg = IPCMessage(
            type=MessageType.DIARIZE,
            payload={"audio_path": "/tmp/test.wav"},
        )
        with patch("diarization.pipeline.DiarizationPipeline", mock_pipeline_cls):
            handle_diarize(msg)

        mock_pipeline_inst.extract_embeddings.assert_called_once_with(
            "/tmp/test.wav", result.segments
        )


# ===========================================================================
# 3. handle_identify_speakers — DB persistence
# ===========================================================================


class TestHandleIdentifySpeakersDB:
    """Tests for DB persistence in the identify_speakers handler."""

    def test_loads_known_embeddings_from_db(self, in_memory_db: DatabaseManager) -> None:
        """Verify the handler loads known embeddings from DB when db_path provided."""
        from ipc.handlers import handle_identify_speakers
        from speaker_id.identifier import SpeakerIdentifier

        # Insert a known speaker with an embedding
        speaker_id = in_memory_db.create_speaker("Alice")
        embedding = [0.1, 0.2, 0.3]
        blob = SpeakerIdentifier.serialize_embedding(embedding)
        in_memory_db.update_speaker_embedding(speaker_id, blob, 1)

        msg = IPCMessage(
            type=MessageType.IDENTIFY_SPEAKERS,
            payload={
                "embeddings": {"SPEAKER_00": [0.1, 0.2, 0.3]},
                "db_path": ":memory:",
            },
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_identify_speakers(msg)

        assert resp.type == ResponseType.SPEAKER_MATCH
        matches = resp.data["matches"]
        assert len(matches) == 1
        assert matches[0]["matched_name"] == "Alice"

    def test_creates_new_speaker_for_unmatched(self, in_memory_db: DatabaseManager) -> None:
        """Verify that unmatched speakers get new DB records."""
        from ipc.handlers import handle_identify_speakers

        msg = IPCMessage(
            type=MessageType.IDENTIFY_SPEAKERS,
            payload={
                "embeddings": {"SPEAKER_00": [0.5, 0.6, 0.7]},
                "db_path": ":memory:",
            },
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_identify_speakers(msg)

        assert resp.type == ResponseType.SPEAKER_MATCH
        # A new speaker should have been created
        speakers = in_memory_db.get_all_speakers()
        assert len(speakers) == 1
        assert speakers[0]["name"] == "SPEAKER_00"

    def test_updates_embedding_for_matched_speaker(self, in_memory_db: DatabaseManager) -> None:
        """Verify matched speakers get their embeddings updated (running average)."""
        from ipc.handlers import handle_identify_speakers
        from speaker_id.identifier import SpeakerIdentifier

        # Create a speaker with an initial embedding
        speaker_id = in_memory_db.create_speaker("Alice")
        initial_embedding = [1.0, 0.0, 0.0]
        blob = SpeakerIdentifier.serialize_embedding(initial_embedding)
        in_memory_db.update_speaker_embedding(speaker_id, blob, 1)

        # Provide a new embedding that matches (identical = cosine sim 1.0)
        msg = IPCMessage(
            type=MessageType.IDENTIFY_SPEAKERS,
            payload={
                "embeddings": {"SPEAKER_00": [1.0, 0.0, 0.0]},
                "db_path": ":memory:",
            },
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_identify_speakers(msg)

        # Verify embedding was updated
        speaker = in_memory_db.get_speaker(speaker_id)
        assert speaker["embedding_count"] == 2

    def test_works_without_db_path(self) -> None:
        """Verify handler works with known_embeddings but no db_path (original behavior)."""
        from ipc.handlers import handle_identify_speakers

        msg = IPCMessage(
            type=MessageType.IDENTIFY_SPEAKERS,
            payload={
                "embeddings": {"SPEAKER_00": [0.1, 0.2]},
                "known_embeddings": {"Alice": [0.1, 0.2]},
            },
        )
        resp = handle_identify_speakers(msg)
        assert resp.type == ResponseType.SPEAKER_MATCH
        assert resp.data["matches"][0]["matched_name"] == "Alice"


# ===========================================================================
# 4. save_summary
# ===========================================================================


class TestHandleSaveSummary:
    """Tests for the save_summary handler."""

    def test_saves_summary_and_returns_id(
        self, in_memory_db: DatabaseManager, tmp_summaries_dir: Path
    ) -> None:
        """Verify save_summary writes a file and creates a DB record."""
        from ipc.handlers import handle_save_summary

        meeting_id = in_memory_db.create_meeting(title="Test Meeting")

        msg = IPCMessage(
            type=MessageType.SAVE_SUMMARY,
            payload={
                "meeting_id": meeting_id,
                "transcript": "Alice said hello.",
                "provider": "claude",
                "model": "claude-sonnet-4-5-20250929",
                "content": "# Meeting Summary\n\nAlice greeted everyone.",
                "speaker_names": ["Alice"],
                "date": "2026-02-09",
            },
        )

        with (
            patch("ipc.handlers._get_db") as mock_get_db,
            patch("ipc.handlers._get_summary_dir") as mock_get_dir,
        ):
            mock_get_db.return_value = in_memory_db
            mock_get_dir.return_value = str(tmp_summaries_dir)
            resp = handle_save_summary(msg)

        assert resp.type == ResponseType.SUMMARY_SAVED
        assert "summary_id" in resp.data
        assert "file_path" in resp.data

        # Verify DB record
        summaries = in_memory_db.get_summaries_for_meeting(meeting_id)
        assert len(summaries) == 1

    def test_returns_error_for_missing_fields(self) -> None:
        """Verify save_summary returns error when required fields are missing."""
        from ipc.handlers import handle_save_summary

        msg = IPCMessage(
            type=MessageType.SAVE_SUMMARY,
            payload={"meeting_id": 1},
        )
        resp = handle_save_summary(msg)
        assert resp.type == ResponseType.ERROR

    def test_writes_markdown_file(
        self, in_memory_db: DatabaseManager, tmp_summaries_dir: Path
    ) -> None:
        """Verify the markdown file is written to disk via SummaryFileManager."""
        from ipc.handlers import handle_save_summary

        meeting_id = in_memory_db.create_meeting(title="Test Meeting")
        content = "# Summary\n\nImportant notes."

        msg = IPCMessage(
            type=MessageType.SAVE_SUMMARY,
            payload={
                "meeting_id": meeting_id,
                "transcript": "Some transcript",
                "provider": "openai",
                "model": "gpt-4",
                "content": content,
                "speaker_names": ["Bob"],
                "date": "2026-02-09",
            },
        )

        with (
            patch("ipc.handlers._get_db") as mock_get_db,
            patch("ipc.handlers._get_summary_dir") as mock_get_dir,
        ):
            mock_get_db.return_value = in_memory_db
            mock_get_dir.return_value = str(tmp_summaries_dir)
            resp = handle_save_summary(msg)

        file_path = resp.data["file_path"]
        assert Path(file_path).exists()
        assert Path(file_path).read_text() == content


# ===========================================================================
# 5. get_all_speakers
# ===========================================================================


class TestHandleGetAllSpeakers:
    """Tests for the get_all_speakers handler."""

    def test_returns_empty_list_when_no_speakers(self, in_memory_db: DatabaseManager) -> None:
        """Verify handler returns empty list when no speakers exist."""
        from ipc.handlers import handle_get_all_speakers

        msg = IPCMessage(type=MessageType.GET_ALL_SPEAKERS, payload={})

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_get_all_speakers(msg)

        assert resp.type == ResponseType.SPEAKERS_LIST
        assert resp.data["speakers"] == []

    def test_returns_speakers_with_meeting_count(self, in_memory_db: DatabaseManager) -> None:
        """Verify handler returns speakers with correct meeting counts."""
        from ipc.handlers import handle_get_all_speakers

        sid1 = in_memory_db.create_speaker("Alice")
        sid2 = in_memory_db.create_speaker("Bob")
        # Alice in 2 meetings, Bob in 1
        mid1 = in_memory_db.create_meeting(title="Meeting 1")
        mid2 = in_memory_db.create_meeting(title="Meeting 2")
        in_memory_db.add_meeting_speaker(mid1, sid1, "SPEAKER_00")
        in_memory_db.add_meeting_speaker(mid2, sid1, "SPEAKER_00")
        in_memory_db.add_meeting_speaker(mid1, sid2, "SPEAKER_01")

        msg = IPCMessage(type=MessageType.GET_ALL_SPEAKERS, payload={})

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_get_all_speakers(msg)

        assert resp.type == ResponseType.SPEAKERS_LIST
        speakers = resp.data["speakers"]
        assert len(speakers) == 2

        alice = next(s for s in speakers if s["name"] == "Alice")
        bob = next(s for s in speakers if s["name"] == "Bob")
        assert alice["meeting_count"] == 2
        assert bob["meeting_count"] == 1


# ===========================================================================
# 6. get_summaries_for_speaker
# ===========================================================================


class TestHandleGetSummariesForSpeaker:
    """Tests for the get_summaries_for_speaker handler."""

    def test_returns_error_for_missing_speaker_name(self) -> None:
        """Verify error when speaker_name is not provided."""
        from ipc.handlers import handle_get_summaries_for_speaker

        msg = IPCMessage(type=MessageType.GET_SUMMARIES_FOR_SPEAKER, payload={})
        resp = handle_get_summaries_for_speaker(msg)
        assert resp.type == ResponseType.ERROR

    def test_returns_summaries_for_speaker(self, in_memory_db: DatabaseManager) -> None:
        """Verify handler returns summaries associated with a speaker."""
        from ipc.handlers import handle_get_summaries_for_speaker

        # Setup: speaker + meeting + meeting_speaker association + summary
        sid = in_memory_db.create_speaker("Alice")
        mid = in_memory_db.create_meeting(title="Meeting 1")
        in_memory_db.add_meeting_speaker(mid, sid, "SPEAKER_00")
        in_memory_db.create_summary(mid, "claude", "claude-sonnet", "# Summary", "/tmp/s.md")

        msg = IPCMessage(
            type=MessageType.GET_SUMMARIES_FOR_SPEAKER,
            payload={"speaker_name": "Alice"},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_get_summaries_for_speaker(msg)

        assert resp.type == ResponseType.SUMMARIES_LIST
        assert len(resp.data["summaries"]) == 1
        assert resp.data["summaries"][0]["meeting_id"] == mid

    def test_returns_empty_for_unknown_speaker(self, in_memory_db: DatabaseManager) -> None:
        """Verify empty list for a speaker name that doesn't exist."""
        from ipc.handlers import handle_get_summaries_for_speaker

        msg = IPCMessage(
            type=MessageType.GET_SUMMARIES_FOR_SPEAKER,
            payload={"speaker_name": "Nobody"},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_get_summaries_for_speaker(msg)

        assert resp.type == ResponseType.SUMMARIES_LIST
        assert resp.data["summaries"] == []


# ===========================================================================
# 7. get_summary_detail
# ===========================================================================


class TestHandleGetSummaryDetail:
    """Tests for the get_summary_detail handler."""

    def test_returns_error_for_missing_summary_id(self) -> None:
        """Verify error when summary_id is not provided."""
        from ipc.handlers import handle_get_summary_detail

        msg = IPCMessage(type=MessageType.GET_SUMMARY_DETAIL, payload={})
        resp = handle_get_summary_detail(msg)
        assert resp.type == ResponseType.ERROR

    def test_returns_full_summary_detail(self, in_memory_db: DatabaseManager) -> None:
        """Verify handler returns complete summary detail."""
        from ipc.handlers import handle_get_summary_detail

        mid = in_memory_db.create_meeting(title="Meeting 1")
        content = "# Meeting Summary\n\nDetailed notes here."
        summary_id = in_memory_db.create_summary(
            mid, "claude", "claude-sonnet", content, "/tmp/summary.md"
        )

        msg = IPCMessage(
            type=MessageType.GET_SUMMARY_DETAIL,
            payload={"summary_id": summary_id},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_get_summary_detail(msg)

        assert resp.type == ResponseType.SUMMARY_DETAIL
        assert resp.data["id"] == summary_id
        assert resp.data["meeting_id"] == mid
        assert resp.data["content"] == content
        assert resp.data["provider"] == "claude"
        assert resp.data["model"] == "claude-sonnet"
        assert resp.data["file_path"] == "/tmp/summary.md"

    def test_returns_error_for_nonexistent_summary(self, in_memory_db: DatabaseManager) -> None:
        """Verify error when summary_id doesn't exist."""
        from ipc.handlers import handle_get_summary_detail

        msg = IPCMessage(
            type=MessageType.GET_SUMMARY_DETAIL,
            payload={"summary_id": 9999},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_get_summary_detail(msg)

        assert resp.type == ResponseType.ERROR
        assert "not found" in resp.data["message"].lower()


# ===========================================================================
# 8. search_summaries
# ===========================================================================


class TestHandleSearchSummaries:
    """Tests for the search_summaries handler."""

    def test_returns_error_for_missing_query(self) -> None:
        """Verify error when query is not provided."""
        from ipc.handlers import handle_search_summaries

        msg = IPCMessage(type=MessageType.SEARCH_SUMMARIES, payload={})
        resp = handle_search_summaries(msg)
        assert resp.type == ResponseType.ERROR

    def test_returns_matching_summaries(self, in_memory_db: DatabaseManager) -> None:
        """Verify FTS search finds matching summaries."""
        from ipc.handlers import handle_search_summaries

        mid = in_memory_db.create_meeting(title="Sprint Review")
        in_memory_db.create_summary(
            mid, "claude", "claude-sonnet", "Alice discussed the sprint review roadmap", None
        )
        in_memory_db.create_summary(
            mid, "claude", "claude-sonnet", "Bob talked about marketing budget", None
        )

        msg = IPCMessage(
            type=MessageType.SEARCH_SUMMARIES,
            payload={"query": "roadmap"},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_search_summaries(msg)

        assert resp.type == ResponseType.SEARCH_RESULTS
        results = resp.data["results"]
        assert len(results) == 1
        assert "roadmap" in results[0]["content"].lower()

    def test_returns_empty_for_no_matches(self, in_memory_db: DatabaseManager) -> None:
        """Verify empty list when no summaries match."""
        from ipc.handlers import handle_search_summaries

        msg = IPCMessage(
            type=MessageType.SEARCH_SUMMARIES,
            payload={"query": "nonexistent"},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_search_summaries(msg)

        assert resp.type == ResponseType.SEARCH_RESULTS
        assert resp.data["results"] == []


# ===========================================================================
# 9. save_settings
# ===========================================================================


class TestHandleSaveSettings:
    """Tests for the save_settings handler."""

    def test_saves_settings_to_db(self, in_memory_db: DatabaseManager) -> None:
        """Verify settings are persisted to the settings table."""
        from ipc.handlers import handle_save_settings

        msg = IPCMessage(
            type=MessageType.SAVE_SETTINGS,
            payload={
                "settings": {
                    "llm_provider": "claude",
                    "model_name": "claude-sonnet-4-5-20250929",
                    "api_key": "sk-test",
                    "audio_device": "MacBook Pro Microphone",
                    "audio_retention": "30",
                }
            },
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_save_settings(msg)

        assert resp.type == ResponseType.SETTINGS_SAVED
        assert resp.data["success"] is True

        # Verify DB
        assert in_memory_db.get_setting("llm_provider") == "claude"
        assert in_memory_db.get_setting("api_key") == "sk-test"

    def test_returns_error_for_missing_settings(self) -> None:
        """Verify error when settings dict is missing."""
        from ipc.handlers import handle_save_settings

        msg = IPCMessage(type=MessageType.SAVE_SETTINGS, payload={})
        resp = handle_save_settings(msg)
        assert resp.type == ResponseType.ERROR

    def test_overwrites_existing_settings(self, in_memory_db: DatabaseManager) -> None:
        """Verify settings can be updated."""
        from ipc.handlers import handle_save_settings

        in_memory_db.set_setting("llm_provider", "openai")

        msg = IPCMessage(
            type=MessageType.SAVE_SETTINGS,
            payload={"settings": {"llm_provider": "claude"}},
        )

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_save_settings(msg)

        assert resp.type == ResponseType.SETTINGS_SAVED
        assert in_memory_db.get_setting("llm_provider") == "claude"


# ===========================================================================
# 10. load_settings
# ===========================================================================


class TestHandleLoadSettings:
    """Tests for the load_settings handler."""

    def test_returns_stored_settings(self, in_memory_db: DatabaseManager) -> None:
        """Verify handler returns settings from DB."""
        from ipc.handlers import handle_load_settings

        in_memory_db.set_setting("llm_provider", "claude")
        in_memory_db.set_setting("model_name", "claude-sonnet-4-5-20250929")

        msg = IPCMessage(type=MessageType.LOAD_SETTINGS, payload={})

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_load_settings(msg)

        assert resp.type == ResponseType.SETTINGS_LOADED
        settings = resp.data["settings"]
        assert settings["llm_provider"] == "claude"
        assert settings["model_name"] == "claude-sonnet-4-5-20250929"

    def test_returns_defaults_for_missing_settings(self, in_memory_db: DatabaseManager) -> None:
        """Verify handler returns default values when no settings are saved."""
        from ipc.handlers import handle_load_settings

        msg = IPCMessage(type=MessageType.LOAD_SETTINGS, payload={})

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_load_settings(msg)

        assert resp.type == ResponseType.SETTINGS_LOADED
        settings = resp.data["settings"]
        # Defaults
        assert settings["llm_provider"] == ""
        assert settings["model_name"] == ""
        assert settings["api_key"] == ""
        assert settings["audio_device"] == ""
        assert settings["audio_retention"] == "30"

    def test_merges_stored_with_defaults(self, in_memory_db: DatabaseManager) -> None:
        """Verify partially stored settings get merged with defaults."""
        from ipc.handlers import handle_load_settings

        in_memory_db.set_setting("llm_provider", "openai")

        msg = IPCMessage(type=MessageType.LOAD_SETTINGS, payload={})

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            resp = handle_load_settings(msg)

        settings = resp.data["settings"]
        assert settings["llm_provider"] == "openai"
        assert settings["audio_retention"] == "30"  # default


# ===========================================================================
# 11. HANDLER_MAP registration
# ===========================================================================


class TestHandlerMapRegistration:
    """Tests that all new handlers are properly registered in HANDLER_MAP."""

    def test_all_new_message_types_in_handler_map(self) -> None:
        """Verify every new MessageType has a corresponding handler."""
        from ipc.handlers import HANDLER_MAP

        new_types = [
            MessageType.SAVE_SUMMARY,
            MessageType.GET_ALL_SPEAKERS,
            MessageType.GET_SUMMARIES_FOR_SPEAKER,
            MessageType.GET_SUMMARY_DETAIL,
            MessageType.SEARCH_SUMMARIES,
            MessageType.SAVE_SETTINGS,
            MessageType.LOAD_SETTINGS,
        ]
        for msg_type in new_types:
            assert msg_type in HANDLER_MAP, f"Missing handler for {msg_type}"

    def test_dispatch_routes_save_summary(self, in_memory_db: DatabaseManager, tmp_summaries_dir: Path) -> None:
        """Verify dispatch routes save_summary through the full path."""
        from main import dispatch

        meeting_id = in_memory_db.create_meeting(title="Test Meeting")

        with (
            patch("ipc.handlers._get_db") as mock_get_db,
            patch("ipc.handlers._get_summary_dir") as mock_get_dir,
        ):
            mock_get_db.return_value = in_memory_db
            mock_get_dir.return_value = str(tmp_summaries_dir)
            result = dispatch({
                "type": "save_summary",
                "meeting_id": meeting_id,
                "transcript": "hello",
                "provider": "claude",
                "model": "claude-sonnet",
                "content": "# Summary",
                "speaker_names": ["Alice"],
                "date": "2026-02-09",
            })

        assert result["type"] == "summary_saved"

    def test_dispatch_routes_get_all_speakers(self, in_memory_db: DatabaseManager) -> None:
        """Verify dispatch routes get_all_speakers."""
        from main import dispatch

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            result = dispatch({"type": "get_all_speakers"})

        assert result["type"] == "speakers_list"

    def test_dispatch_routes_load_settings(self, in_memory_db: DatabaseManager) -> None:
        """Verify dispatch routes load_settings."""
        from main import dispatch

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            result = dispatch({"type": "load_settings"})

        assert result["type"] == "settings_loaded"

    def test_dispatch_routes_save_settings(self, in_memory_db: DatabaseManager) -> None:
        """Verify dispatch routes save_settings."""
        from main import dispatch

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            result = dispatch({
                "type": "save_settings",
                "settings": {"llm_provider": "claude"},
            })

        assert result["type"] == "settings_saved"

    def test_dispatch_routes_search_summaries(self, in_memory_db: DatabaseManager) -> None:
        """Verify dispatch routes search_summaries."""
        from main import dispatch

        with patch("ipc.handlers._get_db") as mock_get_db:
            mock_get_db.return_value = in_memory_db
            result = dispatch({
                "type": "search_summaries",
                "query": "test",
            })

        assert result["type"] == "search_results"
