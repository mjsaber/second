"""Tests for the database module."""

from __future__ import annotations

import pytest

from db.database import DatabaseManager


class TestDatabaseManager:
    """Tests for DatabaseManager initialization and schema."""

    def test_initialize_creates_tables(self, in_memory_db: DatabaseManager) -> None:
        """Verify that initialize() creates the expected tables."""
        cursor = in_memory_db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        assert "speakers" in tables
        assert "meetings" in tables
        assert "meeting_speakers" in tables
        assert "transcript_segments" in tables
        assert "summaries" in tables
        assert "settings" in tables

    def test_initialize_creates_fts_virtual_tables(self, in_memory_db: DatabaseManager) -> None:
        """Verify that FTS5 virtual tables are created."""
        cursor = in_memory_db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in cursor.fetchall()]
        assert "transcript_fts" in tables
        assert "summary_fts" in tables

    def test_connection_property_raises_when_not_initialized(self) -> None:
        """Verify that accessing connection before initialize() raises RuntimeError."""
        db = DatabaseManager()
        try:
            _ = db.connection
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass

    def test_close_and_reinitialize(self) -> None:
        """Verify that a database can be closed and re-initialized."""
        db = DatabaseManager()
        db.initialize()
        db.close()
        db.initialize()
        cursor = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        assert len(cursor.fetchall()) > 0
        db.close()

    def test_foreign_key_constraints_enabled(self, in_memory_db: DatabaseManager) -> None:
        """Verify that foreign key constraints are enforced."""
        # Inserting a meeting_speakers row referencing a non-existent meeting should fail.
        try:
            in_memory_db.connection.execute(
                "INSERT INTO meeting_speakers (meeting_id, speaker_id, diarization_label) "
                "VALUES (999, 999, 'SPEAKER_00')"
            )
            in_memory_db.connection.commit()
            assert False, "Expected foreign key constraint violation"
        except Exception:
            in_memory_db.connection.rollback()

    def test_speakers_crud(self, in_memory_db: DatabaseManager) -> None:
        """Verify basic CRUD operations on the speakers table."""
        conn = in_memory_db.connection

        # Create
        conn.execute("INSERT INTO speakers (name) VALUES (?)", ("Alice",))
        conn.commit()

        # Read
        row = conn.execute("SELECT * FROM speakers WHERE name = ?", ("Alice",)).fetchone()
        assert row is not None
        assert row["name"] == "Alice"
        assert row["embedding_count"] == 0
        assert row["embedding"] is None

        # Update
        conn.execute("UPDATE speakers SET embedding_count = 5 WHERE id = ?", (row["id"],))
        conn.commit()
        updated = conn.execute("SELECT * FROM speakers WHERE id = ?", (row["id"],)).fetchone()
        assert updated["embedding_count"] == 5

        # Delete
        conn.execute("DELETE FROM speakers WHERE id = ?", (row["id"],))
        conn.commit()
        deleted = conn.execute("SELECT * FROM speakers WHERE id = ?", (row["id"],)).fetchone()
        assert deleted is None

    def test_meetings_crud(self, in_memory_db: DatabaseManager) -> None:
        """Verify basic CRUD operations on the meetings table."""
        conn = in_memory_db.connection

        # Create
        conn.execute(
            "INSERT INTO meetings (title, started_at) VALUES (?, datetime('now'))",
            ("Sprint Review",),
        )
        conn.commit()

        # Read
        row = conn.execute("SELECT * FROM meetings WHERE title = ?", ("Sprint Review",)).fetchone()
        assert row is not None
        assert row["title"] == "Sprint Review"
        assert row["status"] == "recording"

        # Update
        conn.execute("UPDATE meetings SET status = 'completed' WHERE id = ?", (row["id"],))
        conn.commit()
        updated = conn.execute("SELECT * FROM meetings WHERE id = ?", (row["id"],)).fetchone()
        assert updated["status"] == "completed"

        # Delete
        conn.execute("DELETE FROM meetings WHERE id = ?", (row["id"],))
        conn.commit()
        deleted = conn.execute("SELECT * FROM meetings WHERE id = ?", (row["id"],)).fetchone()
        assert deleted is None


class TestSpeakerMethods:
    """Tests for DatabaseManager speaker CRUD methods."""

    def test_create_speaker_returns_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify create_speaker returns the new speaker's integer ID."""
        speaker_id = in_memory_db.create_speaker("Alice")
        assert isinstance(speaker_id, int)
        assert speaker_id > 0

    def test_create_speaker_stores_name(self, in_memory_db: DatabaseManager) -> None:
        """Verify the speaker name is persisted in the database."""
        speaker_id = in_memory_db.create_speaker("Bob")
        row = in_memory_db.get_speaker(speaker_id)
        assert row is not None
        assert row["name"] == "Bob"

    def test_create_speaker_defaults_embedding_to_none(self, in_memory_db: DatabaseManager) -> None:
        """Verify new speakers have no embedding and zero embedding count."""
        speaker_id = in_memory_db.create_speaker("Carol")
        row = in_memory_db.get_speaker(speaker_id)
        assert row is not None
        assert row["embedding"] is None
        assert row["embedding_count"] == 0

    def test_get_speaker_returns_none_for_missing_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_speaker returns None when the ID does not exist."""
        result = in_memory_db.get_speaker(9999)
        assert result is None

    def test_get_speaker_by_name_finds_existing(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_speaker_by_name returns the correct speaker row."""
        in_memory_db.create_speaker("Dave")
        row = in_memory_db.get_speaker_by_name("Dave")
        assert row is not None
        assert row["name"] == "Dave"

    def test_get_speaker_by_name_returns_none_for_unknown(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_speaker_by_name returns None for a name not in the database."""
        result = in_memory_db.get_speaker_by_name("Nonexistent")
        assert result is None

    def test_get_all_speakers_returns_empty_list_initially(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_all_speakers returns an empty list when no speakers exist."""
        result = in_memory_db.get_all_speakers()
        assert result == []

    def test_get_all_speakers_returns_all_created(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_all_speakers returns every speaker that was created."""
        in_memory_db.create_speaker("Alice")
        in_memory_db.create_speaker("Bob")
        in_memory_db.create_speaker("Carol")
        result = in_memory_db.get_all_speakers()
        assert len(result) == 3
        names = {row["name"] for row in result}
        assert names == {"Alice", "Bob", "Carol"}

    def test_update_speaker_embedding_stores_blob(self, in_memory_db: DatabaseManager) -> None:
        """Verify update_speaker_embedding persists embedding bytes and count."""
        speaker_id = in_memory_db.create_speaker("Eve")
        embedding = b"\x01\x02\x03\x04"
        in_memory_db.update_speaker_embedding(speaker_id, embedding, 10)
        row = in_memory_db.get_speaker(speaker_id)
        assert row is not None
        assert row["embedding"] == embedding
        assert row["embedding_count"] == 10

    def test_update_speaker_name_changes_name(self, in_memory_db: DatabaseManager) -> None:
        """Verify update_speaker_name modifies the speaker's name."""
        speaker_id = in_memory_db.create_speaker("OldName")
        in_memory_db.update_speaker_name(speaker_id, "NewName")
        row = in_memory_db.get_speaker(speaker_id)
        assert row is not None
        assert row["name"] == "NewName"

    def test_delete_speaker_removes_from_database(self, in_memory_db: DatabaseManager) -> None:
        """Verify delete_speaker removes the speaker so get_speaker returns None."""
        speaker_id = in_memory_db.create_speaker("Temp")
        in_memory_db.delete_speaker(speaker_id)
        assert in_memory_db.get_speaker(speaker_id) is None


class TestMeetingMethods:
    """Tests for DatabaseManager meeting CRUD methods."""

    def test_create_meeting_returns_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify create_meeting returns an integer ID."""
        meeting_id = in_memory_db.create_meeting(title="Standup")
        assert isinstance(meeting_id, int)
        assert meeting_id > 0

    def test_create_meeting_sets_status_to_recording(self, in_memory_db: DatabaseManager) -> None:
        """Verify new meetings default to 'recording' status."""
        meeting_id = in_memory_db.create_meeting()
        row = in_memory_db.get_meeting(meeting_id)
        assert row is not None
        assert row["status"] == "recording"

    def test_create_meeting_sets_started_at(self, in_memory_db: DatabaseManager) -> None:
        """Verify new meetings have a non-null started_at timestamp."""
        meeting_id = in_memory_db.create_meeting()
        row = in_memory_db.get_meeting(meeting_id)
        assert row is not None
        assert row["started_at"] is not None

    def test_create_meeting_with_audio_path(self, in_memory_db: DatabaseManager) -> None:
        """Verify audio_path is stored when provided."""
        meeting_id = in_memory_db.create_meeting(title="Demo", audio_path="/tmp/audio.wav")
        row = in_memory_db.get_meeting(meeting_id)
        assert row is not None
        assert row["audio_path"] == "/tmp/audio.wav"

    def test_create_meeting_without_title(self, in_memory_db: DatabaseManager) -> None:
        """Verify meetings can be created with a null title."""
        meeting_id = in_memory_db.create_meeting()
        row = in_memory_db.get_meeting(meeting_id)
        assert row is not None
        assert row["title"] is None

    def test_get_meeting_returns_none_for_missing_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_meeting returns None for a non-existent meeting."""
        assert in_memory_db.get_meeting(9999) is None

    def test_get_all_meetings_returns_empty_list_initially(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_all_meetings returns an empty list with no meetings."""
        assert in_memory_db.get_all_meetings() == []

    def test_get_all_meetings_returns_all_created(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_all_meetings returns every meeting."""
        in_memory_db.create_meeting(title="Meeting 1")
        in_memory_db.create_meeting(title="Meeting 2")
        result = in_memory_db.get_all_meetings()
        assert len(result) == 2

    def test_update_meeting_status_changes_status(self, in_memory_db: DatabaseManager) -> None:
        """Verify update_meeting_status modifies the status field."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.update_meeting_status(meeting_id, "processing")
        row = in_memory_db.get_meeting(meeting_id)
        assert row is not None
        assert row["status"] == "processing"

    def test_update_meeting_status_rejects_invalid_status(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify update_meeting_status raises ValueError for invalid status."""
        meeting_id = in_memory_db.create_meeting()
        with pytest.raises(ValueError, match="Invalid meeting status"):
            in_memory_db.update_meeting_status(meeting_id, "banana")

    def test_end_meeting_sets_ended_at_and_completed(self, in_memory_db: DatabaseManager) -> None:
        """Verify end_meeting sets ended_at to now and status to 'completed'."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.end_meeting(meeting_id)
        row = in_memory_db.get_meeting(meeting_id)
        assert row is not None
        assert row["status"] == "completed"
        assert row["ended_at"] is not None

    def test_delete_meeting_removes_from_database(self, in_memory_db: DatabaseManager) -> None:
        """Verify delete_meeting removes the meeting."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.delete_meeting(meeting_id)
        assert in_memory_db.get_meeting(meeting_id) is None


class TestMeetingSpeakerMethods:
    """Tests for DatabaseManager meeting-speaker association methods."""

    def test_add_meeting_speaker_creates_association(self, in_memory_db: DatabaseManager) -> None:
        """Verify add_meeting_speaker links a speaker to a meeting."""
        speaker_id = in_memory_db.create_speaker("Alice")
        meeting_id = in_memory_db.create_meeting(title="Standup")
        in_memory_db.add_meeting_speaker(meeting_id, speaker_id, "SPEAKER_00")
        speakers = in_memory_db.get_meeting_speakers(meeting_id)
        assert len(speakers) == 1
        assert speakers[0]["speaker_id"] == speaker_id
        assert speakers[0]["diarization_label"] == "SPEAKER_00"

    def test_get_meeting_speakers_returns_all_speakers_for_meeting(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_meeting_speakers returns all speakers linked to a meeting."""
        s1 = in_memory_db.create_speaker("Alice")
        s2 = in_memory_db.create_speaker("Bob")
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_meeting_speaker(meeting_id, s1, "SPEAKER_00")
        in_memory_db.add_meeting_speaker(meeting_id, s2, "SPEAKER_01")
        speakers = in_memory_db.get_meeting_speakers(meeting_id)
        assert len(speakers) == 2

    def test_get_meeting_speakers_returns_empty_for_no_speakers(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_meeting_speakers returns empty list for meeting with no speakers."""
        meeting_id = in_memory_db.create_meeting()
        assert in_memory_db.get_meeting_speakers(meeting_id) == []

    def test_add_meeting_speaker_rejects_invalid_meeting(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify add_meeting_speaker raises on invalid meeting_id (FK constraint)."""
        speaker_id = in_memory_db.create_speaker("Alice")
        try:
            in_memory_db.add_meeting_speaker(9999, speaker_id, "SPEAKER_00")
            assert False, "Expected an error for invalid meeting_id"
        except Exception:
            pass


class TestTranscriptSegmentMethods:
    """Tests for DatabaseManager transcript segment methods."""

    def test_add_transcript_segment_returns_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify add_transcript_segment returns a segment ID."""
        meeting_id = in_memory_db.create_meeting()
        speaker_id = in_memory_db.create_speaker("Alice")
        seg_id = in_memory_db.add_transcript_segment(
            meeting_id, speaker_id, 0.0, 5.0, "Hello world"
        )
        assert isinstance(seg_id, int)
        assert seg_id > 0

    def test_add_transcript_segment_with_none_speaker(self, in_memory_db: DatabaseManager) -> None:
        """Verify transcript segments can be created with no speaker."""
        meeting_id = in_memory_db.create_meeting()
        seg_id = in_memory_db.add_transcript_segment(
            meeting_id, None, 0.0, 5.0, "Unknown speaker text"
        )
        assert isinstance(seg_id, int)

    def test_add_transcript_segment_with_confidence(self, in_memory_db: DatabaseManager) -> None:
        """Verify confidence value is stored when provided."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_transcript_segment(meeting_id, None, 0.0, 5.0, "Text", confidence=0.95)
        segments = in_memory_db.get_transcript_segments(meeting_id)
        assert len(segments) == 1
        assert segments[0]["confidence"] == 0.95

    def test_get_transcript_segments_ordered_by_start_time(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_transcript_segments returns segments ordered by start_time."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_transcript_segment(meeting_id, None, 10.0, 15.0, "Second")
        in_memory_db.add_transcript_segment(meeting_id, None, 0.0, 5.0, "First")
        in_memory_db.add_transcript_segment(meeting_id, None, 5.0, 10.0, "Middle")
        segments = in_memory_db.get_transcript_segments(meeting_id)
        assert len(segments) == 3
        assert segments[0]["text"] == "First"
        assert segments[1]["text"] == "Middle"
        assert segments[2]["text"] == "Second"

    def test_get_transcript_segments_returns_empty_for_no_segments(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_transcript_segments returns empty list for a meeting with no segments."""
        meeting_id = in_memory_db.create_meeting()
        assert in_memory_db.get_transcript_segments(meeting_id) == []

    def test_update_segment_speaker_changes_speaker_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify update_segment_speaker reassigns the speaker for a segment."""
        meeting_id = in_memory_db.create_meeting()
        s1 = in_memory_db.create_speaker("Alice")
        s2 = in_memory_db.create_speaker("Bob")
        seg_id = in_memory_db.add_transcript_segment(meeting_id, s1, 0.0, 5.0, "Hello")
        in_memory_db.update_segment_speaker(seg_id, s2)
        segments = in_memory_db.get_transcript_segments(meeting_id)
        assert segments[0]["speaker_id"] == s2


class TestSummaryMethods:
    """Tests for DatabaseManager summary methods."""

    def test_create_summary_returns_id(self, in_memory_db: DatabaseManager) -> None:
        """Verify create_summary returns an integer summary ID."""
        meeting_id = in_memory_db.create_meeting()
        summary_id = in_memory_db.create_summary(
            meeting_id, "claude", "claude-sonnet-4-5-20250929", "Summary text here"
        )
        assert isinstance(summary_id, int)
        assert summary_id > 0

    def test_create_summary_with_file_path(self, in_memory_db: DatabaseManager) -> None:
        """Verify create_summary stores file_path when provided."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.create_summary(
            meeting_id,
            "claude",
            "claude-sonnet-4-5-20250929",
            "Summary text",
            file_path="/summaries/2024-01-01.md",
        )
        summaries = in_memory_db.get_summaries_for_meeting(meeting_id)
        assert len(summaries) == 1
        assert summaries[0]["file_path"] == "/summaries/2024-01-01.md"

    def test_get_summaries_for_meeting_returns_only_matching(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_summaries_for_meeting returns only summaries for that meeting."""
        m1 = in_memory_db.create_meeting(title="Meeting 1")
        m2 = in_memory_db.create_meeting(title="Meeting 2")
        in_memory_db.create_summary(m1, "claude", "sonnet", "Summary for m1")
        in_memory_db.create_summary(m2, "openai", "gpt4", "Summary for m2")
        summaries = in_memory_db.get_summaries_for_meeting(m1)
        assert len(summaries) == 1
        assert summaries[0]["content"] == "Summary for m1"

    def test_get_summaries_for_meeting_returns_empty_when_none(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify get_summaries_for_meeting returns empty list when no summaries exist."""
        meeting_id = in_memory_db.create_meeting()
        assert in_memory_db.get_summaries_for_meeting(meeting_id) == []

    def test_get_all_summaries_returns_all(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_all_summaries returns summaries across all meetings."""
        m1 = in_memory_db.create_meeting()
        m2 = in_memory_db.create_meeting()
        in_memory_db.create_summary(m1, "claude", "sonnet", "Summary 1")
        in_memory_db.create_summary(m2, "openai", "gpt4", "Summary 2")
        assert len(in_memory_db.get_all_summaries()) == 2

    def test_get_all_summaries_returns_empty_initially(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_all_summaries returns an empty list with no summaries."""
        assert in_memory_db.get_all_summaries() == []


class TestSettingsMethods:
    """Tests for DatabaseManager settings methods."""

    def test_set_setting_and_get_setting(self, in_memory_db: DatabaseManager) -> None:
        """Verify set_setting stores a value that get_setting retrieves."""
        in_memory_db.set_setting("api_key", "sk-12345")
        assert in_memory_db.get_setting("api_key") == "sk-12345"

    def test_get_setting_returns_none_for_missing_key(self, in_memory_db: DatabaseManager) -> None:
        """Verify get_setting returns None when the key does not exist."""
        assert in_memory_db.get_setting("nonexistent") is None

    def test_set_setting_overwrites_existing_value(self, in_memory_db: DatabaseManager) -> None:
        """Verify set_setting replaces the value for an existing key."""
        in_memory_db.set_setting("theme", "dark")
        in_memory_db.set_setting("theme", "light")
        assert in_memory_db.get_setting("theme") == "light"

    def test_set_setting_handles_multiple_keys(self, in_memory_db: DatabaseManager) -> None:
        """Verify multiple independent settings can coexist."""
        in_memory_db.set_setting("key1", "value1")
        in_memory_db.set_setting("key2", "value2")
        assert in_memory_db.get_setting("key1") == "value1"
        assert in_memory_db.get_setting("key2") == "value2"


class TestSearchMethods:
    """Tests for DatabaseManager FTS5 search methods."""

    def test_search_transcripts_finds_matching_text(self, in_memory_db: DatabaseManager) -> None:
        """Verify search_transcripts finds segments matching the query."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_transcript_segment(
            meeting_id, None, 0.0, 5.0, "The quarterly revenue report looks great"
        )
        in_memory_db.add_transcript_segment(
            meeting_id, None, 5.0, 10.0, "We should discuss the product roadmap"
        )
        results = in_memory_db.search_transcripts("revenue")
        assert len(results) >= 1
        texts = [r["text"] for r in results]
        assert any("revenue" in t for t in texts)

    def test_search_transcripts_returns_empty_for_no_match(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify search_transcripts returns empty list when nothing matches."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_transcript_segment(meeting_id, None, 0.0, 5.0, "Hello world")
        results = in_memory_db.search_transcripts("xyznonexistent")
        assert results == []

    def test_search_summaries_finds_matching_content(self, in_memory_db: DatabaseManager) -> None:
        """Verify search_summaries finds summaries matching the query."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.create_summary(
            meeting_id, "claude", "sonnet", "Discussed quarterly budget allocation"
        )
        in_memory_db.create_summary(
            meeting_id, "claude", "sonnet", "Reviewed product launch timeline"
        )
        results = in_memory_db.search_summaries("budget")
        assert len(results) >= 1
        contents = [r["content"] for r in results]
        assert any("budget" in c for c in contents)

    def test_search_summaries_returns_empty_for_no_match(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify search_summaries returns empty list when nothing matches."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.create_summary(meeting_id, "claude", "sonnet", "Hello world")
        results = in_memory_db.search_summaries("xyznonexistent")
        assert results == []

    def test_search_transcripts_across_multiple_meetings(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify search_transcripts finds segments across different meetings."""
        m1 = in_memory_db.create_meeting()
        m2 = in_memory_db.create_meeting()
        in_memory_db.add_transcript_segment(m1, None, 0.0, 5.0, "Kubernetes deployment strategy")
        in_memory_db.add_transcript_segment(m2, None, 0.0, 5.0, "Kubernetes cluster scaling")
        results = in_memory_db.search_transcripts("Kubernetes")
        assert len(results) == 2


class TestCascadeDeletes:
    """Tests for ON DELETE CASCADE and ON DELETE SET NULL behavior."""

    def test_delete_meeting_cascades_to_transcript_segments(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify deleting a meeting removes its transcript segments."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_transcript_segment(meeting_id, None, 0.0, 5.0, "Hello")
        in_memory_db.add_transcript_segment(meeting_id, None, 5.0, 10.0, "World")
        in_memory_db.delete_meeting(meeting_id)
        segments = in_memory_db.get_transcript_segments(meeting_id)
        assert segments == []

    def test_delete_meeting_cascades_to_summaries(self, in_memory_db: DatabaseManager) -> None:
        """Verify deleting a meeting removes its summaries."""
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.create_summary(meeting_id, "claude", "sonnet", "Summary text")
        in_memory_db.delete_meeting(meeting_id)
        summaries = in_memory_db.get_summaries_for_meeting(meeting_id)
        assert summaries == []

    def test_delete_meeting_cascades_to_meeting_speakers(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify deleting a meeting removes its speaker associations."""
        speaker_id = in_memory_db.create_speaker("Alice")
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_meeting_speaker(meeting_id, speaker_id, "SPEAKER_00")
        in_memory_db.delete_meeting(meeting_id)
        speakers = in_memory_db.get_meeting_speakers(meeting_id)
        assert speakers == []

    def test_delete_speaker_nullifies_transcript_segment_speaker(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify deleting a speaker sets segment speaker_id to NULL."""
        meeting_id = in_memory_db.create_meeting()
        speaker_id = in_memory_db.create_speaker("Alice")
        in_memory_db.add_transcript_segment(meeting_id, speaker_id, 0.0, 5.0, "Hello")
        in_memory_db.delete_speaker(speaker_id)
        segments = in_memory_db.get_transcript_segments(meeting_id)
        assert len(segments) == 1
        assert segments[0]["speaker_id"] is None

    def test_delete_speaker_cascades_to_meeting_speakers(
        self, in_memory_db: DatabaseManager
    ) -> None:
        """Verify deleting a speaker removes meeting_speakers associations."""
        speaker_id = in_memory_db.create_speaker("Alice")
        meeting_id = in_memory_db.create_meeting()
        in_memory_db.add_meeting_speaker(meeting_id, speaker_id, "SPEAKER_00")
        in_memory_db.delete_speaker(speaker_id)
        speakers = in_memory_db.get_meeting_speakers(meeting_id)
        assert speakers == []
