"""Pyannote speaker diarization pipeline.

Segments a recording into speaker turns and extracts per-speaker embeddings
for downstream speaker identification across meetings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


class DiarizationPipeline:
    """Wraps pyannote-audio for speaker diarization.

    Usage:
        pipeline = DiarizationPipeline()
        pipeline.load()
        result = pipeline.diarize("/path/to/audio.wav", num_speakers=2)
    """

    def __init__(self) -> None:
        self._pipeline_loaded = False

    def load(self) -> None:
        """Load the pyannote diarization pipeline.

        Raises:
            RuntimeError: If pyannote-audio is not available.
        """
        # Stub — will load pyannote.audio.Pipeline.from_pretrained()
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

        # Stub — will call self._pipeline(audio_path)
        return DiarizationResult(segments=[], embeddings={})
