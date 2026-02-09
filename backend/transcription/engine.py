"""MLX-Whisper transcription engine.

Wraps the mlx-whisper library to provide streaming transcription of audio chunks.
Runs on Apple Silicon via the MLX framework for low-latency, on-device inference.
"""

from __future__ import annotations

import importlib
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class TranscriptionSegment:
    """A single transcribed segment with timing information.

    Attributes:
        text: The transcribed text.
        start: Start time in seconds.
        end: End time in seconds.
        is_partial: Whether this is a partial (still-updating) result.
    """

    text: str
    start: float
    end: float
    is_partial: bool = False


class TranscriptionEngine:
    """Manages mlx-whisper model loading and audio transcription.

    Usage:
        engine = TranscriptionEngine(model_name="mlx-community/whisper-large-v3-turbo")
        engine.load_model()
        segments = engine.transcribe(audio_bytes)
    """

    def __init__(
        self,
        model_name: str = "mlx-community/whisper-large-v3-turbo",
        language: str = "en",
    ) -> None:
        self.model_name = model_name
        self.language = language
        self._model_loaded = False
        self._mlx_whisper: types.ModuleType | None = None

    def load_model(self) -> None:
        """Load the whisper model into memory via lazy import.

        Raises:
            RuntimeError: If mlx-whisper is not installed.
        """
        try:
            self._mlx_whisper = importlib.import_module("mlx_whisper")
        except ImportError:
            raise RuntimeError("mlx-whisper is not installed. Run: pip install mlx-whisper")
        self._model_loaded = True

    def unload_model(self) -> None:
        """Release model from memory."""
        self._model_loaded = False
        self._mlx_whisper = None

    def _prepare_audio(self, audio_data: bytes) -> np.ndarray:
        """Convert raw 16-bit PCM mono audio bytes to a float32 numpy array.

        The input is expected to be 16kHz, 16-bit signed little-endian PCM mono.
        The output is a float32 array normalized to the [-1, 1] range, as expected
        by mlx-whisper.

        Args:
            audio_data: Raw PCM audio bytes.

        Returns:
            Numpy float32 array normalized to [-1, 1].
        """
        if len(audio_data) == 0:
            return np.array([], dtype=np.float32)
        samples = np.frombuffer(audio_data, dtype=np.int16)
        return samples.astype(np.float32) / 32768.0

    def _parse_segments(self, result: dict[str, Any]) -> list[TranscriptionSegment]:
        """Parse mlx_whisper transcribe() output into TranscriptionSegment list.

        Args:
            result: The dict returned by mlx_whisper.transcribe(), containing
                    a "segments" key with list of dicts having "text", "start", "end".

        Returns:
            List of TranscriptionSegment instances.
        """
        segments: list[TranscriptionSegment] = []
        for seg in result.get("segments", []):
            segments.append(
                TranscriptionSegment(
                    text=seg["text"],
                    start=seg["start"],
                    end=seg["end"],
                )
            )
        return segments

    def transcribe(self, audio_data: bytes, initial_prompt: str = "") -> list[TranscriptionSegment]:
        """Transcribe an audio chunk.

        Args:
            audio_data: Raw audio bytes (16kHz, 16-bit PCM mono).
            initial_prompt: Optional prompt with speaker names for improved accuracy.

        Returns:
            List of transcription segments.

        Raises:
            RuntimeError: If the model is not loaded.
        """
        if not self._model_loaded or self._mlx_whisper is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        audio_array = self._prepare_audio(audio_data)
        result: dict[str, Any] = self._mlx_whisper.transcribe(
            audio_array,
            path_or_hf_repo=self.model_name,
            language=self.language,
            initial_prompt=initial_prompt,
        )
        return self._parse_segments(result)

    def transcribe_file(
        self, audio_path: str | Path, initial_prompt: str = ""
    ) -> list[TranscriptionSegment]:
        """Transcribe audio from a file path.

        This passes the file path directly to mlx_whisper.transcribe(), which
        handles file reading internally. Useful for the post-meeting diarization flow.

        Args:
            audio_path: Path to the audio file.
            initial_prompt: Optional prompt with speaker names for improved accuracy.

        Returns:
            List of transcription segments.

        Raises:
            RuntimeError: If the model is not loaded.
        """
        if not self._model_loaded or self._mlx_whisper is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        path_str = str(audio_path)
        result: dict[str, Any] = self._mlx_whisper.transcribe(
            path_str,
            path_or_hf_repo=self.model_name,
            language=self.language,
            initial_prompt=initial_prompt,
        )
        return self._parse_segments(result)
