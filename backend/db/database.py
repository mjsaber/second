"""SQLite database manager for Second.

Manages the local SQLite database that stores meetings, transcripts,
speaker embeddings, API keys, and application settings.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

VALID_MEETING_STATUSES = {"recording", "processing", "completed"}


class DatabaseManager:
    """Manages SQLite database connections and schema migrations.

    Usage:
        db = DatabaseManager("/path/to/second.db")
        db.initialize()
        # ... use db for queries ...
        db.close()
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file.
                     Use ":memory:" or None for an in-memory database.
        """
        if db_path is None:
            self._db_path = ":memory:"
        else:
            self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Open the database connection and apply schema migrations."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._apply_schema()

    def _apply_schema(self) -> None:
        """Create or migrate database tables."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS speakers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                embedding BLOB,
                embedding_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY,
                title TEXT,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                audio_path TEXT,
                status TEXT DEFAULT 'recording',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS meeting_speakers (
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
                speaker_id INTEGER REFERENCES speakers(id) ON DELETE CASCADE,
                diarization_label TEXT,
                PRIMARY KEY (meeting_id, speaker_id)
            );

            CREATE TABLE IF NOT EXISTS transcript_segments (
                id INTEGER PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
                speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                text TEXT NOT NULL,
                confidence REAL
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                content TEXT NOT NULL,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # FTS5 virtual tables must be created outside executescript
        # because CREATE VIRTUAL TABLE doesn't work reliably inside executescript.
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transcript_fts'"
        )
        if cursor.fetchone() is None:
            self._conn.execute(
                "CREATE VIRTUAL TABLE transcript_fts "
                "USING fts5(text, content=transcript_segments, content_rowid=id)"
            )

        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='summary_fts'"
        )
        if cursor.fetchone() is None:
            self._conn.execute(
                "CREATE VIRTUAL TABLE summary_fts "
                "USING fts5(content, content=summaries, content_rowid=id)"
            )

        # FTS5 sync triggers — keep FTS indexes in sync with content tables.
        # Triggers must be created outside executescript (same reason as virtual tables).
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS transcript_segments_ai
            AFTER INSERT ON transcript_segments BEGIN
                INSERT INTO transcript_fts(rowid, text) VALUES (new.id, new.text);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS transcript_segments_ad
            AFTER DELETE ON transcript_segments BEGIN
                INSERT INTO transcript_fts(transcript_fts, rowid, text)
                    VALUES('delete', old.id, old.text);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS transcript_segments_au
            AFTER UPDATE ON transcript_segments BEGIN
                INSERT INTO transcript_fts(transcript_fts, rowid, text)
                    VALUES('delete', old.id, old.text);
                INSERT INTO transcript_fts(rowid, text) VALUES (new.id, new.text);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS summaries_ai
            AFTER INSERT ON summaries BEGIN
                INSERT INTO summary_fts(rowid, content) VALUES (new.id, new.content);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS summaries_ad
            AFTER DELETE ON summaries BEGIN
                INSERT INTO summary_fts(summary_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS summaries_au
            AFTER UPDATE ON summaries BEGIN
                INSERT INTO summary_fts(summary_fts, rowid, content)
                    VALUES('delete', old.id, old.content);
                INSERT INTO summary_fts(rowid, content) VALUES (new.id, new.content);
            END
        """)

        self._conn.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the active database connection.

        Raises:
            RuntimeError: If the database is not initialized.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Speaker methods
    # ------------------------------------------------------------------

    def create_speaker(self, name: str) -> int:
        """Create a new speaker and return the speaker ID."""
        cursor = self.connection.execute("INSERT INTO speakers (name) VALUES (?)", (name,))
        self.connection.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_speaker(self, speaker_id: int) -> sqlite3.Row | None:
        """Return a speaker row by ID, or None if not found."""
        return self.connection.execute(
            "SELECT * FROM speakers WHERE id = ?", (speaker_id,)
        ).fetchone()

    def get_speaker_by_name(self, name: str) -> sqlite3.Row | None:
        """Return the first speaker row matching the given name, or None."""
        return self.connection.execute("SELECT * FROM speakers WHERE name = ?", (name,)).fetchone()

    def get_all_speakers(self) -> list[sqlite3.Row]:
        """Return all speaker rows."""
        return self.connection.execute("SELECT * FROM speakers").fetchall()

    def update_speaker_embedding(
        self, speaker_id: int, embedding: bytes, embedding_count: int
    ) -> None:
        """Update the embedding blob and count for a speaker."""
        self.connection.execute(
            "UPDATE speakers SET embedding = ?, embedding_count = ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (embedding, embedding_count, speaker_id),
        )
        self.connection.commit()

    def update_speaker_name(self, speaker_id: int, name: str) -> None:
        """Rename a speaker."""
        self.connection.execute(
            "UPDATE speakers SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (name, speaker_id),
        )
        self.connection.commit()

    def delete_speaker(self, speaker_id: int) -> None:
        """Delete a speaker by ID."""
        self.connection.execute("DELETE FROM speakers WHERE id = ?", (speaker_id,))
        self.connection.commit()

    # ------------------------------------------------------------------
    # Meeting methods
    # ------------------------------------------------------------------

    def create_meeting(self, title: str | None = None, audio_path: str | None = None) -> int:
        """Create a new meeting with started_at set to now and status 'recording'."""
        cursor = self.connection.execute(
            "INSERT INTO meetings (title, audio_path, started_at, status) "
            "VALUES (?, ?, datetime('now'), 'recording')",
            (title, audio_path),
        )
        self.connection.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_meeting(self, meeting_id: int) -> sqlite3.Row | None:
        """Return a meeting row by ID, or None if not found."""
        return self.connection.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()

    def get_all_meetings(self) -> list[sqlite3.Row]:
        """Return all meeting rows."""
        return self.connection.execute("SELECT * FROM meetings").fetchall()

    def update_meeting_status(
        self, meeting_id: int, status: Literal["recording", "processing", "completed"]
    ) -> None:
        """Update a meeting's status."""
        if status not in VALID_MEETING_STATUSES:
            raise ValueError(
                f"Invalid meeting status: {status!r}. Must be one of {VALID_MEETING_STATUSES}"
            )
        self.connection.execute(
            "UPDATE meetings SET status = ? WHERE id = ?",
            (status, meeting_id),
        )
        self.connection.commit()

    def end_meeting(self, meeting_id: int) -> None:
        """Mark a meeting as completed and set ended_at to now."""
        self.connection.execute(
            "UPDATE meetings SET ended_at = datetime('now'), status = 'completed' WHERE id = ?",
            (meeting_id,),
        )
        self.connection.commit()

    def delete_meeting(self, meeting_id: int) -> None:
        """Delete a meeting by ID."""
        self.connection.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        self.connection.commit()

    # ------------------------------------------------------------------
    # Meeting-Speaker methods
    # ------------------------------------------------------------------

    def add_meeting_speaker(self, meeting_id: int, speaker_id: int, diarization_label: str) -> None:
        """Associate a speaker with a meeting."""
        self.connection.execute(
            "INSERT INTO meeting_speakers (meeting_id, speaker_id, diarization_label) "
            "VALUES (?, ?, ?)",
            (meeting_id, speaker_id, diarization_label),
        )
        self.connection.commit()

    def get_meeting_speakers(self, meeting_id: int) -> list[sqlite3.Row]:
        """Return all speaker associations for a meeting."""
        return self.connection.execute(
            "SELECT * FROM meeting_speakers WHERE meeting_id = ?",
            (meeting_id,),
        ).fetchall()

    # ------------------------------------------------------------------
    # Transcript Segment methods
    # ------------------------------------------------------------------

    def add_transcript_segment(
        self,
        meeting_id: int,
        speaker_id: int | None,
        start_time: float,
        end_time: float,
        text: str,
        confidence: float | None = None,
    ) -> int:
        """Add a transcript segment and return its ID."""
        cursor = self.connection.execute(
            "INSERT INTO transcript_segments "
            "(meeting_id, speaker_id, start_time, end_time, text, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (meeting_id, speaker_id, start_time, end_time, text, confidence),
        )
        self.connection.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_transcript_segments(self, meeting_id: int) -> list[sqlite3.Row]:
        """Return all transcript segments for a meeting, ordered by start_time."""
        return self.connection.execute(
            "SELECT * FROM transcript_segments WHERE meeting_id = ? ORDER BY start_time",
            (meeting_id,),
        ).fetchall()

    def update_segment_speaker(self, segment_id: int, speaker_id: int) -> None:
        """Reassign a transcript segment to a different speaker."""
        self.connection.execute(
            "UPDATE transcript_segments SET speaker_id = ? WHERE id = ?",
            (speaker_id, segment_id),
        )
        self.connection.commit()

    # ------------------------------------------------------------------
    # Summary methods
    # ------------------------------------------------------------------

    def create_summary(
        self,
        meeting_id: int,
        provider: str,
        model: str,
        content: str,
        file_path: str | None = None,
    ) -> int:
        """Create a summary for a meeting and return its ID."""
        cursor = self.connection.execute(
            "INSERT INTO summaries (meeting_id, provider, model, content, file_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (meeting_id, provider, model, content, file_path),
        )
        self.connection.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_summaries_for_meeting(self, meeting_id: int) -> list[sqlite3.Row]:
        """Return all summaries for a given meeting."""
        return self.connection.execute(
            "SELECT * FROM summaries WHERE meeting_id = ?", (meeting_id,)
        ).fetchall()

    def get_all_summaries(self) -> list[sqlite3.Row]:
        """Return all summary rows."""
        return self.connection.execute("SELECT * FROM summaries").fetchall()

    # ------------------------------------------------------------------
    # Settings methods
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        """Return the value for a setting key, or None if not found."""
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None

    def set_setting(self, key: str, value: str) -> None:
        """Insert or update a setting."""
        self.connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.connection.commit()

    # ------------------------------------------------------------------
    # Search methods (FTS5)
    # ------------------------------------------------------------------

    def search_transcripts(self, query: str) -> list[sqlite3.Row]:
        """Search transcript segments using FTS5 full-text search."""
        return self.connection.execute(
            "SELECT ts.* FROM transcript_segments ts "
            "JOIN transcript_fts fts ON ts.id = fts.rowid "
            "WHERE transcript_fts MATCH ?",
            (query,),
        ).fetchall()

    def search_summaries(self, query: str) -> list[sqlite3.Row]:
        """Search summaries using FTS5 full-text search."""
        return self.connection.execute(
            "SELECT s.* FROM summaries s "
            "JOIN summary_fts fts ON s.id = fts.rowid "
            "WHERE summary_fts MATCH ?",
            (query,),
        ).fetchall()
