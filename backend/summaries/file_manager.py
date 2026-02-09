"""Manages markdown summary file storage organized by person and date."""

from __future__ import annotations

import re
from pathlib import Path

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SummaryFileManager:
    """Manages markdown summary file storage organized by person and date."""

    def __init__(self, base_dir: str | Path) -> None:
        """Initialize with base directory for summaries."""
        self.base_dir = Path(base_dir).resolve()

    def save_summary(self, speaker_name: str, date: str, content: str) -> Path:
        """Save a summary markdown file.

        Args:
            speaker_name: Name of the person (used as directory name, will be sanitized).
            date: Date string in YYYY-MM-DD format.
            content: Markdown content.

        Returns:
            Path to the saved file.
        """
        path = self.get_summary_path(speaker_name, date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def get_summary(self, speaker_name: str, date: str) -> str | None:
        """Read a summary file. Returns None if not found."""
        path = self.get_summary_path(speaker_name, date)
        if not path.exists():
            return None
        return path.read_text()

    def list_speakers(self) -> list[str]:
        """List all speakers who have summaries, sorted alphabetically."""
        if not self.base_dir.exists():
            return []
        return sorted(entry.name for entry in self.base_dir.iterdir() if entry.is_dir())

    def list_summaries_for_speaker(self, speaker_name: str) -> list[str]:
        """List all summary dates for a speaker, sorted chronologically."""
        sanitized = self.sanitize_speaker_name(speaker_name)
        speaker_dir = self.base_dir / sanitized
        if not speaker_dir.exists():
            return []
        return sorted(path.stem for path in speaker_dir.iterdir() if path.suffix == ".md")

    def delete_summary(self, speaker_name: str, date: str) -> bool:
        """Delete a summary file. Returns True if deleted, False if not found."""
        path = self.get_summary_path(speaker_name, date)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def validate_date(date: str) -> None:
        """Validate date is in YYYY-MM-DD format to prevent path traversal."""
        if not _DATE_PATTERN.match(date):
            raise ValueError(
                f"Invalid date format: {date!r}. Must be YYYY-MM-DD (e.g. '2026-02-08')"
            )

    def get_summary_path(self, speaker_name: str, date: str) -> Path:
        """Get the expected path for a summary file (may not exist yet)."""
        self.validate_date(date)
        sanitized = self.sanitize_speaker_name(speaker_name)
        path = (self.base_dir / sanitized / f"{date}.md").resolve()
        # Final path traversal guard: ensure path is within base_dir
        if not str(path).startswith(str(self.base_dir)):
            raise ValueError(f"Path traversal detected: resulting path escapes base directory")
        return path

    @staticmethod
    def sanitize_speaker_name(name: str) -> str:
        """Sanitize speaker name for use as directory name.

        - lowercase
        - replace spaces with underscores
        - remove non-alphanumeric chars (except underscores and hyphens)
        """
        name = name.lower()
        name = name.replace(" ", "_")
        name = re.sub(r"[^a-z0-9_\-]", "", name)
        # Prevent path traversal: strip leading dots and dashes
        name = name.lstrip(".-")
        if not name:
            raise ValueError("Speaker name is empty after sanitization")
        return name
