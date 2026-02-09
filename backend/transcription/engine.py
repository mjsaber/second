"""MLX-Whisper transcription engine.

Wraps the mlx-whisper library to provide streaming transcription of audio chunks.
Runs on Apple Silicon via the MLX framework for low-latency, on-device inference.
"""

from __future__ import annotations

from dataclasses import dataclass


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

    def __init__(self, model_name: str = "mlx-community/whisper-large-v3-turbo") -> None:
        self.model_name = model_name
        self._model_loaded = False

    def load_model(self) -> None:
        """Load the whisper model into memory.

        Raises:
            RuntimeError: If mlx-whisper is not available.
        """
        # Stub — will call mlx_whisper.load_model()
        self._model_loaded = True

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
        if not self._model_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Stub — will call mlx_whisper.transcribe()
        return []

    def unload_model(self) -> None:
        """Release model from memory."""
        self._model_loaded = False
