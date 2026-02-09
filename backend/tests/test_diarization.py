"""Tests for the diarization pipeline module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from diarization.pipeline import (
    DiarizationPipeline,
    DiarizationResult,
    DiarizationSegment,
    assign_speakers_to_words,
)


class TestDiarizationPipeline:
    """Tests for DiarizationPipeline initialization and basic behavior."""

    def test_diarize_raises_without_pipeline_loaded(self) -> None:
        """Verify that diarizing before loading raises RuntimeError."""
        pipeline = DiarizationPipeline()
        with pytest.raises(RuntimeError, match="Pipeline not loaded"):
            pipeline.diarize("/fake/path.wav")

    def test_load_enables_diarization(self) -> None:
        """Verify that load() sets the pipeline to a ready state."""
        mock_pipeline_cls = MagicMock()
        mock_pyannote = MagicMock()
        mock_pyannote.Pipeline = mock_pipeline_cls

        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pyannote}):
            pipeline = DiarizationPipeline()
            pipeline.load()
            assert pipeline._pipeline_loaded is True

    def test_diarize_raises_on_missing_file(self, tmp_path: object) -> None:
        """Verify that diarizing a nonexistent file raises FileNotFoundError."""
        mock_pipeline_cls = MagicMock()
        mock_pyannote = MagicMock()
        mock_pyannote.Pipeline = mock_pipeline_cls

        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pyannote}):
            pipeline = DiarizationPipeline()
            pipeline.load()
            with pytest.raises(FileNotFoundError):
                pipeline.diarize("/nonexistent/audio.wav")

    def test_load_raises_when_pyannote_not_installed(self) -> None:
        """Verify that load() raises RuntimeError when pyannote is not installed."""
        pipeline = DiarizationPipeline()
        with patch.dict("sys.modules", {"pyannote.audio": None, "pyannote": None}):
            with pytest.raises(RuntimeError, match="pyannote-audio"):
                pipeline.load()

    def test_load_succeeds_with_mocked_pyannote(self) -> None:
        """Verify that load() succeeds when pyannote is available (mocked)."""
        mock_pipeline_cls = MagicMock()
        mock_pipeline_instance = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline_instance

        mock_pyannote = MagicMock()
        mock_pyannote.Pipeline = mock_pipeline_cls

        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pyannote}):
            pipeline = DiarizationPipeline()
            pipeline.load()
            assert pipeline._pipeline_loaded is True
            mock_pipeline_cls.from_pretrained.assert_called_once_with(
                "pyannote/speaker-diarization-3.1"
            )

    def test_diarize_parses_pyannote_annotation_into_segments(self, tmp_path: object) -> None:
        """Verify that diarize parses pyannote Annotation into DiarizationSegment list."""
        assert isinstance(tmp_path, type(tmp_path))  # satisfy type checker
        from pathlib import Path

        audio_file = Path(str(tmp_path)) / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        # Build a mock pyannote Annotation with itertracks
        mock_segment_1 = MagicMock()
        mock_segment_1.start = 0.0
        mock_segment_1.end = 2.5

        mock_segment_2 = MagicMock()
        mock_segment_2.start = 2.5
        mock_segment_2.end = 5.0

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = [
            (mock_segment_1, "A", "SPEAKER_00"),
            (mock_segment_2, "B", "SPEAKER_01"),
        ]

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = mock_annotation

        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline_instance

        mock_pyannote = MagicMock()
        mock_pyannote.Pipeline = mock_pipeline_cls

        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pyannote}):
            pipeline = DiarizationPipeline()
            pipeline.load()
            result = pipeline.diarize(str(audio_file))

        assert len(result.segments) == 2
        assert result.segments[0] == DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=2.5)
        assert result.segments[1] == DiarizationSegment(speaker="SPEAKER_01", start=2.5, end=5.0)

    def test_diarize_passes_num_speakers_to_pipeline(self, tmp_path: object) -> None:
        """Verify that diarize passes num_speakers to the pyannote pipeline when provided."""
        from pathlib import Path

        audio_file = Path(str(tmp_path)) / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = []

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = mock_annotation

        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline_instance

        mock_pyannote = MagicMock()
        mock_pyannote.Pipeline = mock_pipeline_cls

        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pyannote}):
            pipeline = DiarizationPipeline()
            pipeline.load()
            pipeline.diarize(str(audio_file), num_speakers=3)

        # The pipeline should have been called with num_speakers=3
        call_kwargs = mock_pipeline_instance.call_args
        assert call_kwargs is not None
        assert call_kwargs[1].get("num_speakers") == 3

    def test_diarize_omits_num_speakers_when_none(self, tmp_path: object) -> None:
        """Verify that diarize does not pass num_speakers when it is None."""
        from pathlib import Path

        audio_file = Path(str(tmp_path)) / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        mock_annotation = MagicMock()
        mock_annotation.itertracks.return_value = []

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.return_value = mock_annotation

        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline_instance

        mock_pyannote = MagicMock()
        mock_pyannote.Pipeline = mock_pipeline_cls

        with patch.dict("sys.modules", {"pyannote": MagicMock(), "pyannote.audio": mock_pyannote}):
            pipeline = DiarizationPipeline()
            pipeline.load()
            pipeline.diarize(str(audio_file), num_speakers=None)

        call_kwargs = mock_pipeline_instance.call_args
        assert call_kwargs is not None
        assert "num_speakers" not in call_kwargs[1]

    def test_extract_embeddings_returns_per_speaker_vectors(self, tmp_path: object) -> None:
        """Verify that extract_embeddings returns embedding vectors keyed by speaker."""
        from pathlib import Path

        audio_file = Path(str(tmp_path)) / "test.wav"
        audio_file.write_bytes(b"fake audio data")

        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=2.0),
            DiarizationSegment(speaker="SPEAKER_01", start=2.0, end=4.0),
        ]

        mock_embedding = MagicMock()
        mock_embedding.data = MagicMock()

        # Mock the Inference class
        mock_inference_instance = MagicMock()

        # Simulate crop returning embeddings, then mean collapsing them
        import numpy as np

        fake_embedding_00 = np.array([0.1, 0.2, 0.3])
        fake_embedding_01 = np.array([0.4, 0.5, 0.6])

        def mock_crop(file_info, segment):
            """Return different embeddings based on segment start time."""
            if segment.start == 0.0:
                return np.array([fake_embedding_00])
            return np.array([fake_embedding_01])

        mock_inference_instance.crop = mock_crop

        mock_inference_cls = MagicMock(return_value=mock_inference_instance)

        mock_pyannote_audio = MagicMock()
        mock_pyannote_audio.Inference = mock_inference_cls

        mock_pyannote_audio_mod = MagicMock()
        mock_pyannote_audio_mod.Inference = mock_inference_cls

        with patch.dict(
            "sys.modules",
            {
                "pyannote": MagicMock(),
                "pyannote.audio": mock_pyannote_audio,
            },
        ):
            pipeline = DiarizationPipeline()
            # Set pipeline loaded state without actually calling load
            pipeline._pipeline_loaded = True
            pipeline._pipeline = MagicMock()

            with patch(
                "diarization.pipeline._lazy_import_inference",
                return_value=mock_inference_cls,
            ):
                embeddings = pipeline.extract_embeddings(str(audio_file), segments)

        assert "SPEAKER_00" in embeddings
        assert "SPEAKER_01" in embeddings
        assert isinstance(embeddings["SPEAKER_00"], list)
        assert isinstance(embeddings["SPEAKER_01"], list)


class TestDiarizationSegment:
    """Tests for the DiarizationSegment data class."""

    def test_segment_stores_speaker_and_timing(self) -> None:
        """Verify that segment fields are correctly stored."""
        seg = DiarizationSegment(speaker="SPEAKER_00", start=1.5, end=3.2)
        assert seg.speaker == "SPEAKER_00"
        assert seg.start == 1.5
        assert seg.end == 3.2

    def test_segment_equality(self) -> None:
        """Verify that two segments with the same values are equal."""
        seg1 = DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=1.0)
        seg2 = DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=1.0)
        assert seg1 == seg2

    def test_segment_inequality(self) -> None:
        """Verify that two segments with different values are not equal."""
        seg1 = DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=1.0)
        seg2 = DiarizationSegment(speaker="SPEAKER_01", start=0.0, end=1.0)
        assert seg1 != seg2


class TestDiarizationResult:
    """Tests for the DiarizationResult data class."""

    def test_empty_result(self) -> None:
        """Verify that an empty result can be constructed."""
        result = DiarizationResult(segments=[], embeddings={})
        assert len(result.segments) == 0
        assert len(result.embeddings) == 0

    def test_result_with_segments_and_embeddings(self) -> None:
        """Verify that a result with segments and embeddings stores them correctly."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=2.0),
            DiarizationSegment(speaker="SPEAKER_01", start=2.0, end=4.0),
        ]
        embeddings = {
            "SPEAKER_00": [0.1, 0.2, 0.3],
            "SPEAKER_01": [0.4, 0.5, 0.6],
        }
        result = DiarizationResult(segments=segments, embeddings=embeddings)
        assert len(result.segments) == 2
        assert result.segments[0].speaker == "SPEAKER_00"
        assert result.embeddings["SPEAKER_01"] == [0.4, 0.5, 0.6]


class TestAssignSpeakersToWords:
    """Tests for the assign_speakers_to_words function."""

    def test_assigns_correct_speaker_by_max_overlap(self) -> None:
        """Verify that a word is assigned the speaker with maximum temporal overlap."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=3.0),
            DiarizationSegment(speaker="SPEAKER_01", start=2.5, end=6.0),
        ]
        # Word from 2.0 to 3.5: overlaps SPEAKER_00 by 1.0s (2.0-3.0), SPEAKER_01 by 1.0s (2.5-3.5)
        # Word from 1.0 to 2.0: overlaps SPEAKER_00 by 1.0s, no overlap with SPEAKER_01
        # Word from 4.0 to 5.0: overlaps SPEAKER_01 by 1.0s, no overlap with SPEAKER_00
        words = [
            {"start": 1.0, "end": 2.0, "text": "hello"},
            {"start": 4.0, "end": 5.0, "text": "world"},
        ]
        result = assign_speakers_to_words(segments, words)
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[1]["speaker"] == "SPEAKER_01"
        # Original fields are preserved
        assert result[0]["text"] == "hello"
        assert result[1]["text"] == "world"

    def test_assigns_speaker_with_greater_overlap_when_word_spans_two_speakers(self) -> None:
        """Verify that when a word spans two speakers, the one with more overlap wins."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=2.0),
            DiarizationSegment(speaker="SPEAKER_01", start=2.0, end=5.0),
        ]
        # Word from 1.5 to 3.0: overlaps SPEAKER_00 by 0.5s (1.5-2.0), SPEAKER_01 by 1.0s (2.0-3.0)
        words = [{"start": 1.5, "end": 3.0, "text": "overlap"}]
        result = assign_speakers_to_words(segments, words)
        assert result[0]["speaker"] == "SPEAKER_01"

    def test_handles_word_with_no_overlapping_speaker(self) -> None:
        """Verify that a word with no overlapping speaker gets None as speaker."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=1.0),
        ]
        words = [{"start": 5.0, "end": 6.0, "text": "lonely"}]
        result = assign_speakers_to_words(segments, words)
        assert result[0]["speaker"] is None
        assert result[0]["text"] == "lonely"

    def test_handles_empty_segments_list(self) -> None:
        """Verify that all words get None speaker when there are no segments."""
        segments: list[DiarizationSegment] = []
        words = [
            {"start": 0.0, "end": 1.0, "text": "hello"},
            {"start": 1.0, "end": 2.0, "text": "world"},
        ]
        result = assign_speakers_to_words(segments, words)
        assert result[0]["speaker"] is None
        assert result[1]["speaker"] is None

    def test_handles_empty_words_list(self) -> None:
        """Verify that an empty words list returns an empty result."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=5.0),
        ]
        words: list[dict[str, object]] = []
        result = assign_speakers_to_words(segments, words)
        assert result == []

    def test_does_not_mutate_input_words(self) -> None:
        """Verify that the original word dicts are not modified."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=5.0),
        ]
        words = [{"start": 0.0, "end": 1.0, "text": "hello"}]
        result = assign_speakers_to_words(segments, words)
        assert "speaker" not in words[0]
        assert "speaker" in result[0]

    def test_multiple_words_assigned_to_correct_speakers(self) -> None:
        """Verify correct assignment across a realistic multi-speaker scenario."""
        segments = [
            DiarizationSegment(speaker="SPEAKER_00", start=0.0, end=3.0),
            DiarizationSegment(speaker="SPEAKER_01", start=3.0, end=6.0),
            DiarizationSegment(speaker="SPEAKER_00", start=6.0, end=9.0),
        ]
        words = [
            {"start": 0.5, "end": 1.0, "text": "I"},
            {"start": 1.0, "end": 1.5, "text": "think"},
            {"start": 3.5, "end": 4.0, "text": "no"},
            {"start": 4.0, "end": 4.5, "text": "way"},
            {"start": 7.0, "end": 7.5, "text": "yes"},
        ]
        result = assign_speakers_to_words(segments, words)
        assert result[0]["speaker"] == "SPEAKER_00"
        assert result[1]["speaker"] == "SPEAKER_00"
        assert result[2]["speaker"] == "SPEAKER_01"
        assert result[3]["speaker"] == "SPEAKER_01"
        assert result[4]["speaker"] == "SPEAKER_00"
