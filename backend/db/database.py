"""SQLite database manager for Second.

Manages the local SQLite database that stores meetings, transcripts,
speaker embeddings, API keys, and application settings.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


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
                meeting_id INTEGER REFERENCES meetings(id),
                speaker_id INTEGER REFERENCES speakers(id),
                diarization_label TEXT,
                PRIMARY KEY (meeting_id, speaker_id)
            );

            CREATE TABLE IF NOT EXISTS transcript_segments (
                id INTEGER PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(id),
                speaker_id INTEGER REFERENCES speakers(id),
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                text TEXT NOT NULL,
                confidence REAL
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(id),
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
