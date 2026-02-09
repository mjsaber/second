"""Tests for the transcription engine module."""

from __future__ import annotations

import pytest

from transcription.engine import TranscriptionEngine, TranscriptionSegment


class TestTranscriptionEngine:
    """Tests for TranscriptionEngine initialization and basic behavior."""

    def test_engine_initializes_with_default_model(self) -> None:
        """Verify that the engine has a sensible default model name."""
        engine = TranscriptionEngine()
        assert "whisper" in engine.model_name

    def test_transcribe_raises_without_model_loaded(self) -> None:
        """Verify that transcribing before loading raises RuntimeError."""
        engine = TranscriptionEngine()
        with pytest.raises(RuntimeError, match="Model not loaded"):
            engine.transcribe(b"fake audio data")

    def test_load_model_enables_transcription(self) -> None:
        """Verify that load_model sets the engine to a ready state."""
        engine = TranscriptionEngine()
        engine.load_model()
        # Should not raise — stub returns empty list
        result = engine.transcribe(b"fake audio data")
        assert isinstance(result, list)

    def test_unload_model_prevents_transcription(self) -> None:
        """Verify that unload_model resets the engine state."""
        engine = TranscriptionEngine()
        engine.load_model()
        engine.unload_model()
        with pytest.raises(RuntimeError):
            engine.transcribe(b"fake audio data")


class TestTranscriptionSegment:
    """Tests for the TranscriptionSegment data class."""

    def test_segment_defaults_to_non_partial(self) -> None:
        """Verify that segments are non-partial by default."""
        segment = TranscriptionSegment(text="hello", start=0.0, end=1.0)
        assert segment.is_partial is False
