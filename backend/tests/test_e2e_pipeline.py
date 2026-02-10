"""End-to-end pipeline tests exercising IPC handlers with a real database.

These tests verify the full integration path through the IPC dispatch layer:
health checks, transcription, settings round-trip, summary save/get/search,
and speaker listing. Heavy ML models (TranscriptionEngine, DiarizationPipeline)
are mocked since we are testing integration plumbing, not ML inference.
"""

from __future__ import annotations

import base64
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from db.database import DatabaseManager
from ipc.protocol import IPCMessage, IPCResponse, MessageType, ResponseType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TEST_WAV = FIXTURE_DIR / "test_speech.wav"


@pytest.fixture()
def e2e_db() -> DatabaseManager:
    """Provide a fresh in-memory database for each test."""
    db = DatabaseManager(db_path=None)
    db.initialize()
    yield db  # type: ignore[misc]
    db.close()


@pytest.fixture(autouse=True)
def _patch_db_and_summaries(e2e_db: DatabaseManager, tmp_path: Path) -> None:
    """Patch _get_db and _get_summary_dir so handlers use the test database and temp dir."""
    with (
        patch("ipc.handlers._get_db", return_value=e2e_db),
        patch("ipc.handlers._get_summary_dir", return_value=str(tmp_path)),
    ):
        yield  # type: ignore[misc]


@pytest.fixture()
def mock_transcription_engine() -> MagicMock:
    """Create a mock TranscriptionEngine that returns a canned transcription result."""
    mock_engine_cls = MagicMock()
    mock_engine_inst = MagicMock()
    mock_engine_inst.transcribe.return_value = [
        MagicMock(text=" Hello world", start=0.0, end=1.5, is_partial=False),
    ]
    mock_engine_cls.return_value = mock_engine_inst
    return mock_engine_cls


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _dispatch(message: dict) -> dict:
    """Dispatch a raw message dict through the IPC layer and return the response dict."""
    from main import dispatch

    return dispatch(message)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify the health endpoint returns a well-formed ok response."""

    def test_health_returns_ok(self) -> None:
        """Send a health message and verify the response."""
        result = _dispatch({"type": "health"})
        assert result["type"] == "health"
        assert result["status"] == "ok"


class TestTranscription:
    """Verify transcribe_chunk handler processes base64 audio without error."""

    def test_transcribe_chunk_with_mock_engine(
        self, mock_transcription_engine: MagicMock
    ) -> None:
        """Base64-encode the test WAV, send through handle_transcribe_chunk,
        and verify it returns a transcription response."""
        assert TEST_WAV.exists(), f"Test fixture not found: {TEST_WAV}"

        audio_bytes = TEST_WAV.read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        with patch(
            "transcription.engine.TranscriptionEngine", mock_transcription_engine
        ):
            result = _dispatch(
                {
                    "type": "transcribe_chunk",
                    "audio_base64": audio_b64,
                    "initial_prompt": "test meeting",
                }
            )

        assert result["type"] == "transcription"
        assert "text" in result
        assert "segments" in result
        assert isinstance(result["segments"], list)
        assert result["text"] == "Hello world"
        assert result["is_partial"] is False

    def test_transcribe_chunk_with_raw_pcm_bytes(
        self, mock_transcription_engine: MagicMock
    ) -> None:
        """Send a small raw PCM payload (not a full WAV) through the handler."""
        # 8 samples of silence as raw 16-bit PCM
        raw_pcm = struct.pack("<8h", 0, 0, 0, 0, 0, 0, 0, 0)
        audio_b64 = base64.b64encode(raw_pcm).decode("ascii")

        with patch(
            "transcription.engine.TranscriptionEngine", mock_transcription_engine
        ):
            result = _dispatch(
                {"type": "transcribe_chunk", "audio_base64": audio_b64}
            )

        assert result["type"] == "transcription"

    def test_transcribe_chunk_missing_audio_returns_error(self) -> None:
        """Omitting audio_base64 should produce an error response."""
        result = _dispatch({"type": "transcribe_chunk"})
        assert result["type"] == "error"
        assert "audio_base64" in result["message"]


class TestSettingsRoundTrip:
    """Verify saving and loading settings through the IPC layer."""

    def test_save_and_load_settings(self) -> None:
        """Save settings, then load them back and verify the round-trip."""
        save_result = _dispatch(
            {
                "type": "save_settings",
                "settings": {
                    "llm_provider": "claude",
                    "model_name": "claude-sonnet-4-5-20250929",
                    "api_key": "sk-test-key-12345",
                },
            }
        )
        assert save_result["type"] == "settings_saved"
        assert save_result["success"] is True

        load_result = _dispatch({"type": "load_settings"})
        assert load_result["type"] == "settings_loaded"
        assert load_result["settings"]["llm_provider"] == "claude"
        assert load_result["settings"]["model_name"] == "claude-sonnet-4-5-20250929"
        assert load_result["settings"]["api_key"] == "sk-test-key-12345"

    def test_load_settings_returns_defaults_when_empty(self) -> None:
        """Loading settings from an empty DB should return default values."""
        load_result = _dispatch({"type": "load_settings"})
        assert load_result["type"] == "settings_loaded"
        settings = load_result["settings"]
        # All default keys should be present
        assert "llm_provider" in settings
        assert "model_name" in settings
        assert "api_key" in settings
        assert "audio_device" in settings
        assert "audio_retention" in settings
        # Defaults are empty strings or "30" for retention
        assert settings["audio_retention"] == "30"

    def test_save_settings_missing_field_returns_error(self) -> None:
        """Omitting the settings dict should produce an error."""
        result = _dispatch({"type": "save_settings"})
        assert result["type"] == "error"
        assert "settings" in result["message"]

    def test_save_settings_overwrites_previous(self) -> None:
        """Saving the same key twice should overwrite the first value."""
        _dispatch(
            {"type": "save_settings", "settings": {"llm_provider": "openai"}}
        )
        _dispatch(
            {"type": "save_settings", "settings": {"llm_provider": "claude"}}
        )
        load_result = _dispatch({"type": "load_settings"})
        assert load_result["settings"]["llm_provider"] == "claude"


class TestSaveSummary:
    """Verify saving a summary writes to both the database and the file system."""

    def test_save_summary_returns_id_and_file_path(
        self, e2e_db: DatabaseManager, tmp_path: Path
    ) -> None:
        """Save a summary through the IPC handler and verify the response."""
        meeting_id = e2e_db.create_meeting(title="Test Meeting")

        result = _dispatch(
            {
                "type": "save_summary",
                "meeting_id": meeting_id,
                "provider": "claude",
                "model": "claude-sonnet-4-5-20250929",
                "content": "# Meeting Summary\n\nDiscussed project roadmap and deadlines.",
                "speaker_names": ["Alice"],
                "date": "2026-02-10",
            }
        )

        assert result["type"] == "summary_saved"
        assert "summary_id" in result
        assert isinstance(result["summary_id"], int)
        assert "file_path" in result

        # Verify file was actually written
        saved_path = Path(result["file_path"])
        assert saved_path.exists()
        content = saved_path.read_text()
        assert "project roadmap" in content

    def test_save_summary_missing_fields_returns_error(self) -> None:
        """Omitting required fields should produce an error."""
        result = _dispatch(
            {"type": "save_summary", "meeting_id": 1, "provider": "claude"}
        )
        assert result["type"] == "error"


class TestGetSummary:
    """Verify retrieving a saved summary through the IPC layer."""

    def test_get_summary_detail_returns_content(
        self, e2e_db: DatabaseManager
    ) -> None:
        """Save a summary directly in the DB, then retrieve it via IPC."""
        meeting_id = e2e_db.create_meeting(title="Detail Test")
        summary_id = e2e_db.create_summary(
            meeting_id,
            "claude",
            "claude-sonnet-4-5-20250929",
            "# Full Summary\n\nAction items discussed.",
        )

        result = _dispatch(
            {"type": "get_summary_detail", "summary_id": summary_id}
        )

        assert result["type"] == "summary_detail"
        assert result["id"] == summary_id
        assert result["meeting_id"] == meeting_id
        assert "Action items discussed" in result["content"]

    def test_get_summary_detail_missing_id_returns_error(self) -> None:
        """Omitting summary_id should produce an error."""
        result = _dispatch({"type": "get_summary_detail"})
        assert result["type"] == "error"
        assert "summary_id" in result["message"]

    def test_get_summary_detail_nonexistent_returns_error(self) -> None:
        """Requesting a non-existent summary should produce an error."""
        result = _dispatch(
            {"type": "get_summary_detail", "summary_id": 99999}
        )
        assert result["type"] == "error"
        assert "not found" in result["message"].lower()


class TestSearchSummaries:
    """Verify FTS5 search through the IPC layer."""

    def test_search_summaries_finds_saved_summary(
        self, e2e_db: DatabaseManager
    ) -> None:
        """Insert a summary, then search for a keyword it contains."""
        meeting_id = e2e_db.create_meeting(title="Search Test")
        e2e_db.create_summary(
            meeting_id,
            "claude",
            "sonnet",
            "Discussed quarterly budget allocation and hiring plans",
        )

        result = _dispatch(
            {"type": "search_summaries", "query": "budget"}
        )

        assert result["type"] == "search_results"
        assert len(result["results"]) >= 1
        assert any(
            "budget" in r["content"] for r in result["results"]
        )

    def test_search_summaries_returns_empty_for_no_match(
        self, e2e_db: DatabaseManager
    ) -> None:
        """Searching for a non-existent term should return empty results."""
        meeting_id = e2e_db.create_meeting()
        e2e_db.create_summary(
            meeting_id, "claude", "sonnet", "Some unrelated content"
        )

        result = _dispatch(
            {"type": "search_summaries", "query": "xyznonexistent"}
        )

        assert result["type"] == "search_results"
        assert result["results"] == []

    def test_search_summaries_missing_query_returns_error(self) -> None:
        """Omitting the query field should produce an error."""
        result = _dispatch({"type": "search_summaries"})
        assert result["type"] == "error"
        assert "query" in result["message"]

    def test_search_summaries_finds_across_multiple_meetings(
        self, e2e_db: DatabaseManager
    ) -> None:
        """Verify search finds summaries across different meetings."""
        m1 = e2e_db.create_meeting(title="Meeting A")
        m2 = e2e_db.create_meeting(title="Meeting B")
        e2e_db.create_summary(m1, "claude", "sonnet", "Kubernetes deployment strategy")
        e2e_db.create_summary(m2, "openai", "gpt4", "Kubernetes cluster scaling")

        result = _dispatch(
            {"type": "search_summaries", "query": "Kubernetes"}
        )

        assert result["type"] == "search_results"
        assert len(result["results"]) == 2


class TestGetAllSpeakers:
    """Verify listing all speakers through the IPC layer."""

    def test_get_all_speakers_empty_database(self) -> None:
        """An empty database should return an empty speakers list."""
        result = _dispatch({"type": "get_all_speakers"})
        assert result["type"] == "speakers_list"
        assert result["speakers"] == []

    def test_get_all_speakers_returns_created_speakers(
        self, e2e_db: DatabaseManager
    ) -> None:
        """Create some speakers, then verify they appear in the listing."""
        e2e_db.create_speaker("Alice")
        e2e_db.create_speaker("Bob")

        result = _dispatch({"type": "get_all_speakers"})

        assert result["type"] == "speakers_list"
        assert len(result["speakers"]) == 2
        names = {s["name"] for s in result["speakers"]}
        assert names == {"Alice", "Bob"}

    def test_get_all_speakers_includes_meeting_count(
        self, e2e_db: DatabaseManager
    ) -> None:
        """Verify that each speaker entry includes a meeting_count field."""
        alice_id = e2e_db.create_speaker("Alice")
        meeting_id = e2e_db.create_meeting(title="Standup")
        e2e_db.add_meeting_speaker(meeting_id, alice_id, "SPEAKER_00")

        result = _dispatch({"type": "get_all_speakers"})

        alice = next(s for s in result["speakers"] if s["name"] == "Alice")
        assert alice["meeting_count"] == 1


class TestFullPipelineFlow:
    """Test a realistic end-to-end flow: create meeting -> save summary -> search -> speakers."""

    def test_complete_flow(
        self, e2e_db: DatabaseManager, mock_transcription_engine: MagicMock
    ) -> None:
        """Run through the full pipeline flow and verify each step."""
        # 1. Health check
        health = _dispatch({"type": "health"})
        assert health["type"] == "health"
        assert health["status"] == "ok"

        # 2. Save settings
        settings_save = _dispatch(
            {
                "type": "save_settings",
                "settings": {"llm_provider": "claude", "api_key": "sk-test"},
            }
        )
        assert settings_save["type"] == "settings_saved"

        # 3. Verify settings round-trip
        settings_load = _dispatch({"type": "load_settings"})
        assert settings_load["settings"]["llm_provider"] == "claude"

        # 4. Transcribe audio (mocked)
        raw_pcm = struct.pack("<8h", 0, 100, 200, 300, 400, 300, 200, 100)
        audio_b64 = base64.b64encode(raw_pcm).decode("ascii")
        with patch(
            "transcription.engine.TranscriptionEngine", mock_transcription_engine
        ):
            transcription = _dispatch(
                {
                    "type": "transcribe_chunk",
                    "audio_base64": audio_b64,
                    "initial_prompt": "Alice Bob standup",
                }
            )
        assert transcription["type"] == "transcription"
        assert "text" in transcription

        # 5. Create meeting and speakers in the database
        meeting_id = e2e_db.create_meeting(title="Sprint Review")
        alice_id = e2e_db.create_speaker("Alice")
        bob_id = e2e_db.create_speaker("Bob")
        e2e_db.add_meeting_speaker(meeting_id, alice_id, "SPEAKER_00")
        e2e_db.add_meeting_speaker(meeting_id, bob_id, "SPEAKER_01")

        # 6. Save a summary through IPC
        summary_save = _dispatch(
            {
                "type": "save_summary",
                "meeting_id": meeting_id,
                "provider": "claude",
                "model": "claude-sonnet-4-5-20250929",
                "content": (
                    "# Meeting: Alice & Bob -- 2026-02-10\n\n"
                    "## Summary\n"
                    "Discussed sprint velocity and upcoming feature releases.\n\n"
                    "## Action Items\n"
                    "- [ ] Alice: Update the dashboard\n"
                    "- [ ] Bob: Review pull requests\n"
                ),
                "speaker_names": ["Alice", "Bob"],
                "date": "2026-02-10",
            }
        )
        assert summary_save["type"] == "summary_saved"
        summary_id = summary_save["summary_id"]

        # 7. Retrieve the saved summary
        detail = _dispatch(
            {"type": "get_summary_detail", "summary_id": summary_id}
        )
        assert detail["type"] == "summary_detail"
        assert "sprint velocity" in detail["content"]

        # 8. Search summaries via FTS
        search = _dispatch(
            {"type": "search_summaries", "query": "velocity"}
        )
        assert search["type"] == "search_results"
        assert len(search["results"]) >= 1
        assert any("velocity" in r["content"] for r in search["results"])

        # 9. Get all speakers
        speakers = _dispatch({"type": "get_all_speakers"})
        assert speakers["type"] == "speakers_list"
        assert len(speakers["speakers"]) == 2
        speaker_names = {s["name"] for s in speakers["speakers"]}
        assert speaker_names == {"Alice", "Bob"}

        # Verify Alice has 1 meeting associated
        alice_data = next(
            s for s in speakers["speakers"] if s["name"] == "Alice"
        )
        assert alice_data["meeting_count"] == 1
