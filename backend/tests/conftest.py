"""Shared test fixtures for the Second backend test suite."""

from __future__ import annotations

import sqlite3

import pytest

from db.database import DatabaseManager


@pytest.fixture
def in_memory_db() -> DatabaseManager:
    """Provide an initialized in-memory SQLite database for test isolation."""
    db = DatabaseManager(db_path=None)
    db.initialize()
    yield db  # type: ignore[misc]
    db.close()


@pytest.fixture
def raw_sqlite_conn() -> sqlite3.Connection:
    """Provide a raw SQLite in-memory connection for low-level tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn  # type: ignore[misc]
    conn.close()
