"""Pyannote speaker diarization pipeline.

Segments a recording into speaker turns and extracts per-speaker embeddings
for downstream speaker identification across meetings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DiarizationSegment:
    """A single speaker turn in the audio.

    Attributes:
        speaker: Speaker label (e.g. "SPEAKER_00").
        start: Start time in seconds.
        end: End time in seconds.
    """

    speaker: str
    start: float
    end: float


@dataclass
class DiarizationResult:
    """Complete diarization output for a recording.

    Attributes:
        segments: Ordered list of speaker turns.
        embeddings: Per-speaker embedding vectors for speaker identification.
    """

    segments: list[DiarizationSegment]
    embeddings: dict[str, list[float]]


def _lazy_import_pipeline() -> Any:
    """Lazy-import pyannote.audio.Pipeline.

    Raises:
        RuntimeError: If pyannote-audio is not installed.
    """
    try:
        from pyannote.audio import Pipeline  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError):
        msg = (
            "pyannote-audio is required for diarization but is not installed. "
            "Install it with: pip install pyannote-audio"
        )
        raise RuntimeError(msg)
    return Pipeline


def _lazy_import_inference() -> Any:
    """Lazy-import pyannote.audio.Inference.

    Raises:
        RuntimeError: If pyannote-audio is not installed.
    """
    try:
        from pyannote.audio import Inference  # type: ignore[import-not-found]
    except (ImportError, ModuleNotFoundError):
        msg = (
            "pyannote-audio is required for speaker embeddings but is not installed. "
            "Install it with: pip install pyannote-audio"
        )
        raise RuntimeError(msg)
    return Inference


class DiarizationPipeline:
    """Wraps pyannote-audio for speaker diarization.

    Usage:
        pipeline = DiarizationPipeline()
        pipeline.load()
        result = pipeline.diarize("/path/to/audio.wav", num_speakers=2)
    """

    def __init__(self) -> None:
        self._pipeline_loaded = False
        self._pipeline: Any = None

    def load(self) -> None:
        """Load the pyannote diarization pipeline.

        Raises:
            RuntimeError: If pyannote-audio is not available.
        """
        pipeline_cls = _lazy_import_pipeline()
        self._pipeline = pipeline_cls.from_pretrained("pyannote/speaker-diarization-3.1")
        self._pipeline_loaded = True

    def diarize(
        self,
        audio_path: str | Path,
        num_speakers: int | None = None,
    ) -> DiarizationResult:
        """Run diarization on an audio file.

        Args:
            audio_path: Path to the WAV audio file.
            num_speakers: Expected number of speakers (None for auto-detect).

        Returns:
            Diarization result with segments and speaker embeddings.

        Raises:
            RuntimeError: If the pipeline is not loaded.
            FileNotFoundError: If the audio file does not exist.
        """
        if not self._pipeline_loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        kwargs: dict[str, Any] = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers

        annotation = self._pipeline(str(audio_path), **kwargs)

        segments: list[DiarizationSegment] = []
        for segment, _track, label in annotation.itertracks(yield_label=True):
            segments.append(
                DiarizationSegment(
                    speaker=label,
                    start=segment.start,
                    end=segment.end,
                )
            )

        return DiarizationResult(segments=segments, embeddings={})

    def extract_embeddings(
        self,
        audio_path: str | Path,
        segments: list[DiarizationSegment],
    ) -> dict[str, list[float]]:
        """Extract per-speaker wespeaker embeddings from the diarization output.

        Args:
            audio_path: Path to the WAV audio file.
            segments: List of diarization segments to extract embeddings from.

        Returns:
            Dictionary mapping speaker labels to embedding vectors.

        Raises:
            RuntimeError: If the pipeline is not loaded.
        """
        if not self._pipeline_loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")

        import numpy as np

        inference_cls = _lazy_import_inference()
        inference = inference_cls(model="pyannote/wespeaker-voxceleb-resnet34-LM", window="whole")

        # Group segments by speaker
        speaker_segments: dict[str, list[DiarizationSegment]] = {}
        for seg in segments:
            speaker_segments.setdefault(seg.speaker, []).append(seg)

        embeddings: dict[str, list[float]] = {}
        for speaker, speaker_segs in speaker_segments.items():
            # Collect embeddings from all segments for this speaker
            speaker_embeddings = []
            for seg in speaker_segs:
                # Create a pyannote-style Segment for cropping
                crop_segment = type("Segment", (), {"start": seg.start, "end": seg.end})()
                embedding = inference.crop(str(audio_path), crop_segment)
                speaker_embeddings.append(embedding)

            # Average all embeddings for this speaker
            if speaker_embeddings:
                mean_embedding = np.mean(np.vstack(speaker_embeddings), axis=0)
                embeddings[speaker] = mean_embedding.tolist()

        return embeddings


def assign_speakers_to_words(
    segments: list[DiarizationSegment],
    words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign speaker labels to transcribed words based on maximum temporal overlap.

    Uses a simple O(n*m) approach: for each word, compute the overlap with every
    segment and assign the speaker with the greatest overlap.

    Args:
        segments: Diarization segments with speaker labels.
        words: List of word dicts with "start", "end", "text" keys.

    Returns:
        New list of word dicts with an added "speaker" key. Words with no
        overlapping segment get speaker=None.
    """
    result: list[dict[str, Any]] = []

    for word in words:
        word_start = word["start"]
        word_end = word["end"]

        best_speaker: str | None = None
        best_overlap: float = 0.0

        for seg in segments:
            # Compute overlap: max(0, min(word_end, seg_end) - max(word_start, seg_start))
            overlap_start = max(word_start, seg.start)
            overlap_end = min(word_end, seg.end)
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = seg.speaker

        labeled_word = {**word, "speaker": best_speaker}
        result.append(labeled_word)

    return result
