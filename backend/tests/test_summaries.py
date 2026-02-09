"""Tests for the summary file management module."""

from __future__ import annotations

from pathlib import Path

import pytest

from summaries.file_manager import SummaryFileManager


class TestSaveSummary:
    """Tests for saving summary files."""

    def test_save_summary_creates_file_at_correct_path(self, tmp_path: Path) -> None:
        """Verify that save_summary writes a file at {base}/{speaker}/{date}.md."""
        manager = SummaryFileManager(tmp_path)
        result = manager.save_summary("alice", "2026-02-08", "# Meeting Notes\nHello.")
        expected = tmp_path / "alice" / "2026-02-08.md"
        assert result == expected
        assert expected.exists()
        assert expected.read_text() == "# Meeting Notes\nHello."

    def test_save_summary_creates_speaker_directory_if_not_exists(self, tmp_path: Path) -> None:
        """Verify that save_summary creates the speaker directory automatically."""
        manager = SummaryFileManager(tmp_path)
        manager.save_summary("bob", "2026-02-03", "Notes for Bob.")
        assert (tmp_path / "bob").is_dir()

    def test_save_summary_overwrites_existing_file_for_same_date(self, tmp_path: Path) -> None:
        """Verify that saving again for the same speaker+date overwrites the file."""
        manager = SummaryFileManager(tmp_path)
        manager.save_summary("alice", "2026-02-01", "First version.")
        manager.save_summary("alice", "2026-02-01", "Updated version.")
        content = (tmp_path / "alice" / "2026-02-01.md").read_text()
        assert content == "Updated version."


class TestGetSummary:
    """Tests for reading summary files."""

    def test_get_summary_returns_content_for_existing_file(self, tmp_path: Path) -> None:
        """Verify that get_summary returns the markdown content of an existing file."""
        manager = SummaryFileManager(tmp_path)
        manager.save_summary("alice", "2026-02-08", "# Notes\nContent here.")
        result = manager.get_summary("alice", "2026-02-08")
        assert result == "# Notes\nContent here."

    def test_get_summary_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Verify that get_summary returns None when the file does not exist."""
        manager = SummaryFileManager(tmp_path)
        result = manager.get_summary("nobody", "2026-01-01")
        assert result is None


class TestListSpeakers:
    """Tests for listing speakers."""

    def test_list_speakers_returns_empty_list_initially(self, tmp_path: Path) -> None:
        """Verify that list_speakers returns an empty list when no summaries exist."""
        manager = SummaryFileManager(tmp_path)
        assert manager.list_speakers() == []

    def test_list_speakers_returns_all_speaker_directories(self, tmp_path: Path) -> None:
        """Verify that list_speakers returns sorted names of all speaker directories."""
        manager = SummaryFileManager(tmp_path)
        manager.save_summary("charlie", "2026-02-01", "Notes.")
        manager.save_summary("alice", "2026-02-01", "Notes.")
        manager.save_summary("bob", "2026-02-01", "Notes.")
        speakers = manager.list_speakers()
        assert speakers == ["alice", "bob", "charlie"]


class TestListSummariesForSpeaker:
    """Tests for listing summaries by speaker."""

    def test_list_summaries_for_speaker_returns_sorted_dates(self, tmp_path: Path) -> None:
        """Verify that summaries are returned in chronological order."""
        manager = SummaryFileManager(tmp_path)
        manager.save_summary("alice", "2026-02-15", "Third.")
        manager.save_summary("alice", "2026-02-01", "First.")
        manager.save_summary("alice", "2026-02-08", "Second.")
        dates = manager.list_summaries_for_speaker("alice")
        assert dates == ["2026-02-01", "2026-02-08", "2026-02-15"]

    def test_list_summaries_for_speaker_returns_empty_for_unknown_speaker(
        self, tmp_path: Path
    ) -> None:
        """Verify that an unknown speaker returns an empty list instead of an error."""
        manager = SummaryFileManager(tmp_path)
        assert manager.list_summaries_for_speaker("unknown") == []


class TestDeleteSummary:
    """Tests for deleting summary files."""

    def test_delete_summary_removes_file_and_returns_true(self, tmp_path: Path) -> None:
        """Verify that delete_summary removes the file and returns True."""
        manager = SummaryFileManager(tmp_path)
        manager.save_summary("alice", "2026-02-08", "To be deleted.")
        result = manager.delete_summary("alice", "2026-02-08")
        assert result is True
        assert not (tmp_path / "alice" / "2026-02-08.md").exists()

    def test_delete_summary_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        """Verify that delete_summary returns False when the file does not exist."""
        manager = SummaryFileManager(tmp_path)
        result = manager.delete_summary("alice", "2026-02-08")
        assert result is False


class TestSanitizeSpeakerName:
    """Tests for speaker name sanitization."""

    def test_sanitize_speaker_name_lowercases_and_replaces_spaces(self) -> None:
        """Verify that names are lowercased and spaces become underscores."""
        assert SummaryFileManager.sanitize_speaker_name("Alice Smith") == "alice_smith"

    def test_sanitize_speaker_name_removes_special_characters(self) -> None:
        """Verify that non-alphanumeric chars (except underscores/hyphens) are stripped."""
        assert SummaryFileManager.sanitize_speaker_name("O'Brien (Jr.)") == "obrien_jr"
        assert SummaryFileManager.sanitize_speaker_name("../evil") == "evil"
        assert SummaryFileManager.sanitize_speaker_name("a/b\\c") == "abc"


class TestGetSummaryPath:
    """Tests for getting the expected summary file path."""

    def test_get_summary_path_returns_correct_path_without_creating_file(
        self, tmp_path: Path
    ) -> None:
        """Verify that get_summary_path returns the expected path but does not create it."""
        manager = SummaryFileManager(tmp_path)
        path = manager.get_summary_path("alice", "2026-02-08")
        assert path == tmp_path.resolve() / "alice" / "2026-02-08.md"
        assert not path.exists()


class TestSecurityValidation:
    """Tests for path traversal and input validation security."""

    def test_date_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Verify that date with path traversal characters is rejected."""
        manager = SummaryFileManager(tmp_path)
        with pytest.raises(ValueError, match="Invalid date format"):
            manager.save_summary("alice", "../../etc/passwd", "malicious")

    def test_date_with_slashes_rejected(self, tmp_path: Path) -> None:
        """Verify that date containing slashes is rejected."""
        manager = SummaryFileManager(tmp_path)
        with pytest.raises(ValueError, match="Invalid date format"):
            manager.get_summary("alice", "../secrets")

    def test_date_must_be_yyyy_mm_dd_format(self, tmp_path: Path) -> None:
        """Verify that only strict YYYY-MM-DD format is accepted."""
        manager = SummaryFileManager(tmp_path)
        with pytest.raises(ValueError, match="Invalid date format"):
            manager.get_summary_path("alice", "2026/02/08")
        with pytest.raises(ValueError, match="Invalid date format"):
            manager.get_summary_path("alice", "not-a-date")
        # Valid date should not raise
        manager.get_summary_path("alice", "2026-02-08")

    def test_empty_speaker_name_raises_valueerror(self) -> None:
        """Verify that an empty speaker name raises ValueError."""
        with pytest.raises(ValueError, match="empty after sanitization"):
            SummaryFileManager.sanitize_speaker_name("")

    def test_all_special_chars_speaker_name_raises_valueerror(self) -> None:
        """Verify that a name of only special chars raises ValueError."""
        with pytest.raises(ValueError, match="empty after sanitization"):
            SummaryFileManager.sanitize_speaker_name("...")
        with pytest.raises(ValueError, match="empty after sanitization"):
            SummaryFileManager.sanitize_speaker_name("///")
