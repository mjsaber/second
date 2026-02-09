"""Shared test fixtures for the Second backend test suite."""

from __future__ import annotations

import pytest

from db.database import DatabaseManager


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    """Provide an initialized in-memory SQLite database for test isolation."""
    db = DatabaseManager(db_path=None)
    db.initialize()
    yield db  # type: ignore[misc]
    db.close()
