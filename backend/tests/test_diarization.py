"""Tests for the diarization pipeline module."""

from __future__ import annotations

import pytest

from diarization.pipeline import DiarizationPipeline, DiarizationResult, DiarizationSegment


class TestDiarizationPipeline:
    """Tests for DiarizationPipeline initialization and basic behavior."""

    def test_diarize_raises_without_pipeline_loaded(self) -> None:
        """Verify that diarizing before loading raises RuntimeError."""
        pipeline = DiarizationPipeline()
        with pytest.raises(RuntimeError, match="Pipeline not loaded"):
            pipeline.diarize("/fake/path.wav")

    def test_load_enables_diarization(self) -> None:
        """Verify that load() sets the pipeline to a ready state."""
        pipeline = DiarizationPipeline()
        pipeline.load()
        assert pipeline._pipeline_loaded is True

    def test_diarize_raises_on_missing_file(self, tmp_path: object) -> None:
        """Verify that diarizing a nonexistent file raises FileNotFoundError."""
        pipeline = DiarizationPipeline()
        pipeline.load()
        with pytest.raises(FileNotFoundError):
            pipeline.diarize("/nonexistent/audio.wav")


class TestDiarizationSegment:
    """Tests for the DiarizationSegment data class."""

    def test_segment_stores_speaker_and_timing(self) -> None:
        """Verify that segment fields are correctly stored."""
        seg = DiarizationSegment(speaker="SPEAKER_00", start=1.5, end=3.2)
        assert seg.speaker == "SPEAKER_00"
        assert seg.start == 1.5
        assert seg.end == 3.2


class TestDiarizationResult:
    """Tests for the DiarizationResult data class."""

    def test_empty_result(self) -> None:
        """Verify that an empty result can be constructed."""
        result = DiarizationResult(segments=[], embeddings={})
        assert len(result.segments) == 0
        assert len(result.embeddings) == 0
