"""Tests for the database module."""

from __future__ import annotations

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
