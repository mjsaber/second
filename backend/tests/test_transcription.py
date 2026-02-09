"""Tests for the transcription engine module."""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
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
        mock_mlx = MagicMock()
        mock_mlx.transcribe.return_value = {"text": "", "segments": []}
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx}):
            engine.load_model()
        # Should not raise — returns empty list
        audio_bytes = struct.pack("<4h", 0, 0, 0, 0)
        result = engine.transcribe(audio_bytes)
        assert isinstance(result, list)

    def test_unload_model_prevents_transcription(self) -> None:
        """Verify that unload_model resets the engine state."""
        mock_mlx = MagicMock()
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx}):
            engine.load_model()
        engine.unload_model()
        with pytest.raises(RuntimeError):
            engine.transcribe(b"fake audio data")

    def test_engine_initializes_with_default_language(self) -> None:
        """Verify that the engine defaults to English language."""
        engine = TranscriptionEngine()
        assert engine.language == "en"

    def test_engine_accepts_custom_language(self) -> None:
        """Verify that a custom language can be set at construction."""
        engine = TranscriptionEngine(language="ja")
        assert engine.language == "ja"

    def test_engine_accepts_custom_model_name(self) -> None:
        """Verify that a custom model name can be set at construction."""
        engine = TranscriptionEngine(model_name="mlx-community/whisper-tiny")
        assert engine.model_name == "mlx-community/whisper-tiny"

    def test_load_model_raises_when_mlx_whisper_not_installed(self) -> None:
        """Verify that load_model raises RuntimeError when mlx_whisper is unavailable."""
        engine = TranscriptionEngine()
        # Ensure mlx_whisper cannot be imported
        with patch.dict(sys.modules, {"mlx_whisper": None}):
            with pytest.raises(RuntimeError, match="mlx-whisper is not installed"):
                engine.load_model()

    def test_load_model_succeeds_when_mlx_whisper_available(self) -> None:
        """Verify that load_model succeeds when mlx_whisper is importable."""
        mock_mlx_whisper = MagicMock()
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
        assert engine._model_loaded is True

    def test_transcribe_parses_mlx_whisper_output_into_segments(self) -> None:
        """Verify transcribe converts mlx_whisper result into TranscriptionSegment list."""
        mock_mlx_whisper = MagicMock()
        mock_mlx_whisper.transcribe.return_value = {
            "text": "Hello world",
            "segments": [
                {"text": " Hello", "start": 0.0, "end": 0.5},
                {"text": " world", "start": 0.5, "end": 1.0},
            ],
        }
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
            # Build valid 16-bit PCM audio (4 samples of silence)
            audio_bytes = struct.pack("<4h", 0, 0, 0, 0)
            segments = engine.transcribe(audio_bytes)

        assert len(segments) == 2
        assert segments[0].text == " Hello"
        assert segments[0].start == 0.0
        assert segments[0].end == 0.5
        assert segments[1].text == " world"
        assert segments[1].start == 0.5
        assert segments[1].end == 1.0
        assert all(not seg.is_partial for seg in segments)

    def test_transcribe_passes_initial_prompt_to_mlx_whisper(self) -> None:
        """Verify that the initial_prompt is forwarded to mlx_whisper.transcribe()."""
        mock_mlx_whisper = MagicMock()
        mock_mlx_whisper.transcribe.return_value = {"text": "", "segments": []}
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
            audio_bytes = struct.pack("<4h", 0, 0, 0, 0)
            engine.transcribe(audio_bytes, initial_prompt="Alice Bob standup")

        call_kwargs = mock_mlx_whisper.transcribe.call_args
        assert call_kwargs[1]["initial_prompt"] == "Alice Bob standup"

    def test_transcribe_passes_language_to_mlx_whisper(self) -> None:
        """Verify that the configured language is forwarded to mlx_whisper.transcribe()."""
        mock_mlx_whisper = MagicMock()
        mock_mlx_whisper.transcribe.return_value = {"text": "", "segments": []}
        engine = TranscriptionEngine(language="ja")
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
            audio_bytes = struct.pack("<4h", 0, 0, 0, 0)
            engine.transcribe(audio_bytes)

        call_kwargs = mock_mlx_whisper.transcribe.call_args
        assert call_kwargs[1]["language"] == "ja"

    def test_unload_model_releases_mlx_whisper_reference(self) -> None:
        """Verify that unload_model clears the internal mlx_whisper module reference."""
        mock_mlx_whisper = MagicMock()
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
        assert engine._mlx_whisper is not None
        engine.unload_model()
        assert engine._mlx_whisper is None
        assert engine._model_loaded is False

    def test_transcribe_file_reads_file_and_delegates_to_mlx_whisper(self) -> None:
        """Verify that transcribe_file reads a file path and passes audio to mlx_whisper."""
        mock_mlx_whisper = MagicMock()
        mock_mlx_whisper.transcribe.return_value = {
            "text": "From file",
            "segments": [{"text": " From file", "start": 0.0, "end": 1.5}],
        }
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
            segments = engine.transcribe_file("/tmp/test.wav")

        # transcribe_file should call mlx_whisper.transcribe with the file path string
        mock_mlx_whisper.transcribe.assert_called_once()
        call_args = mock_mlx_whisper.transcribe.call_args
        assert call_args[0][0] == "/tmp/test.wav"
        assert len(segments) == 1
        assert segments[0].text == " From file"

    def test_transcribe_file_accepts_path_object(self) -> None:
        """Verify that transcribe_file accepts a Path object as well as a string."""
        mock_mlx_whisper = MagicMock()
        mock_mlx_whisper.transcribe.return_value = {"text": "", "segments": []}
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
            engine.transcribe_file(Path("/tmp/test.wav"))

        call_args = mock_mlx_whisper.transcribe.call_args
        assert call_args[0][0] == "/tmp/test.wav"

    def test_transcribe_file_raises_when_model_not_loaded(self) -> None:
        """Verify that transcribe_file raises RuntimeError when model not loaded."""
        engine = TranscriptionEngine()
        with pytest.raises(RuntimeError, match="Model not loaded"):
            engine.transcribe_file("/tmp/test.wav")

    def test_transcribe_file_passes_initial_prompt(self) -> None:
        """Verify that transcribe_file forwards initial_prompt to mlx_whisper."""
        mock_mlx_whisper = MagicMock()
        mock_mlx_whisper.transcribe.return_value = {"text": "", "segments": []}
        engine = TranscriptionEngine()
        with patch.dict(sys.modules, {"mlx_whisper": mock_mlx_whisper}):
            engine.load_model()
            engine.transcribe_file("/tmp/test.wav", initial_prompt="Sprint review")

        call_kwargs = mock_mlx_whisper.transcribe.call_args
        assert call_kwargs[1]["initial_prompt"] == "Sprint review"


class TestPrepareAudio:
    """Tests for the _prepare_audio method that converts PCM bytes to numpy arrays."""

    def test_converts_16bit_pcm_to_float32_array(self) -> None:
        """Verify that 16-bit PCM bytes are converted to a float32 numpy array."""
        engine = TranscriptionEngine()
        # 4 samples of 16-bit signed PCM
        audio_bytes = struct.pack("<4h", 0, 16384, -16384, 32767)
        result = engine._prepare_audio(audio_bytes)
        assert result.dtype == np.float32
        assert len(result) == 4

    def test_normalizes_pcm_values_to_minus_one_to_one(self) -> None:
        """Verify that PCM values are normalized to the [-1, 1] range."""
        engine = TranscriptionEngine()
        # Max positive and max negative 16-bit values
        audio_bytes = struct.pack("<2h", 32767, -32768)
        result = engine._prepare_audio(audio_bytes)
        assert result[0] == pytest.approx(32767 / 32768.0, abs=1e-5)
        assert result[1] == pytest.approx(-32768 / 32768.0, abs=1e-5)

    def test_silence_converts_to_zeros(self) -> None:
        """Verify that silent PCM audio (all zeros) produces a zero array."""
        engine = TranscriptionEngine()
        audio_bytes = struct.pack("<4h", 0, 0, 0, 0)
        result = engine._prepare_audio(audio_bytes)
        np.testing.assert_array_equal(result, np.zeros(4, dtype=np.float32))

    def test_empty_audio_returns_empty_array(self) -> None:
        """Verify that empty bytes input produces an empty numpy array."""
        engine = TranscriptionEngine()
        result = engine._prepare_audio(b"")
        assert result.dtype == np.float32
        assert len(result) == 0


class TestTranscriptionSegment:
    """Tests for the TranscriptionSegment data class."""

    def test_segment_defaults_to_non_partial(self) -> None:
        """Verify that segments are non-partial by default."""
        segment = TranscriptionSegment(text="hello", start=0.0, end=1.0)
        assert segment.is_partial is False

    def test_segment_stores_all_fields(self) -> None:
        """Verify that all TranscriptionSegment fields are stored correctly."""
        segment = TranscriptionSegment(text="test", start=1.5, end=3.0, is_partial=True)
        assert segment.text == "test"
        assert segment.start == 1.5
        assert segment.end == 3.0
        assert segment.is_partial is True


class TestHandleTranscribeChunkIntegration:
    """Tests for the IPC handler integration with transcription response format."""

    def test_handler_returns_segments_list_in_response(self) -> None:
        """Verify that handle_transcribe_chunk returns segments in the response."""
        from ipc.handlers import handle_transcribe_chunk
        from ipc.protocol import IPCMessage, MessageType

        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": "AAAAAAAAAAA="},
        )
        resp = handle_transcribe_chunk(msg)
        result = resp.to_dict()
        assert result["type"] == "transcription"
        assert "text" in result
        assert "segments" in result
        assert "is_partial" in result
        assert isinstance(result["segments"], list)

    def test_handler_decodes_base64_audio(self) -> None:
        """Verify that handle_transcribe_chunk base64-decodes the audio payload."""
        import base64

        from ipc.handlers import handle_transcribe_chunk
        from ipc.protocol import IPCMessage, MessageType

        # Encode some known bytes
        raw_audio = struct.pack("<4h", 0, 0, 0, 0)
        encoded = base64.b64encode(raw_audio).decode()
        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": encoded},
        )
        resp = handle_transcribe_chunk(msg)
        # Should succeed without error
        assert resp.type != "error"
