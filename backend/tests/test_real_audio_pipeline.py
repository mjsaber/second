"""E2E tests for the Python sidecar pipeline using REAL audio files.

Spawns the sidecar as a subprocess (just like Tauri would), communicates via
JSON-over-stdin/stdout, and verifies that real transcription produces correct
results for both English and Chinese audio.

These tests require:
- The backend venv with mlx-whisper installed
- Apple Silicon (MLX backend)
- Test fixture WAV files in backend/tests/fixtures/

Run with:
    cd backend && .venv/bin/python -m pytest tests/test_real_audio_pipeline.py -v -s

All tests are marked @pytest.mark.slow because they involve model loading and
real ML inference.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import threading
import wave
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
MAIN_PY = BACKEND_DIR / "main.py"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
TEST_ENGLISH_WAV = FIXTURE_DIR / "test_english.wav"
TEST_CHINESE_WAV = FIXTURE_DIR / "test_chinese.wav"

# First transcription may need to download the model — allow up to 120s.
FIRST_TIMEOUT_S = 120
# Subsequent transcriptions with a warm model should be faster.
WARM_TIMEOUT_S = 60

# Expected key words in the English transcription (case-insensitive check).
ENGLISH_KEY_WORDS = [
    "meeting",
    "product",
    "launch",
    "budget",
    "engineering",
    "customer",
    "feedback",
    "sarah",
    "timeline",
]

# Expected key words in the Chinese transcription.
CHINESE_KEY_WORDS = [
    "会议",
    "产品",
    "发布",
    "预算",
    "工程",
    "客户",
    "反馈",
]

# Minimum fraction of key words that must appear for a test to pass.
# Whisper may occasionally miss a word, so we allow some tolerance.
MIN_KEYWORD_RATIO = 0.6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_wav_pcm(wav_path: Path) -> tuple[bytes, int, int, int]:
    """Read a WAV file and return (raw_pcm_bytes, n_channels, sample_width, framerate).

    The returned bytes are raw signed 16-bit little-endian PCM with no header.
    """
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        framerate = wf.getframerate()
        pcm_bytes = wf.readframes(wf.getnframes())
    return pcm_bytes, n_channels, sample_width, framerate


def _pcm_to_wav_bytes(pcm_data: bytes, n_channels: int, sample_width: int, framerate: int) -> bytes:
    """Wrap raw PCM data in a valid WAV container and return the bytes.

    This is needed for chunked tests: each chunk must be a valid WAV so the
    sidecar's handler (which expects WAV-format bytes) can process it.  In
    practice the sidecar's TranscriptionEngine._prepare_audio expects raw PCM,
    so we actually send raw PCM for full-file tests.  For chunked tests we
    still send raw PCM since that's what the handler decodes.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(framerate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _split_pcm_into_chunks(
    pcm_bytes: bytes,
    sample_width: int,
    n_channels: int,
    framerate: int,
    chunk_duration_s: float = 5.0,
) -> list[bytes]:
    """Split raw PCM bytes into fixed-duration chunks.

    Each chunk is returned as raw PCM bytes (not WAV-wrapped).
    The last chunk may be shorter than chunk_duration_s.
    """
    bytes_per_sample = sample_width * n_channels
    samples_per_chunk = int(framerate * chunk_duration_s)
    bytes_per_chunk = samples_per_chunk * bytes_per_sample

    chunks: list[bytes] = []
    offset = 0
    while offset < len(pcm_bytes):
        end = min(offset + bytes_per_chunk, len(pcm_bytes))
        chunks.append(pcm_bytes[offset:end])
        offset = end
    return chunks


# ---------------------------------------------------------------------------
# Sidecar fixture
# ---------------------------------------------------------------------------


class SidecarProcess:
    """Manages a sidecar subprocess and provides JSON IPC helpers."""

    def __init__(self, proc: subprocess.Popen[bytes]) -> None:
        self._proc = proc
        self._lock = threading.Lock()

    def send_message(self, msg: dict[str, Any], timeout: float = WARM_TIMEOUT_S) -> dict[str, Any]:
        """Send a JSON message to the sidecar and return the parsed response.

        Args:
            msg: The message dict (must contain a "type" key).
            timeout: Max seconds to wait for the response line.

        Returns:
            Parsed JSON response dict.

        Raises:
            TimeoutError: If no response is received within *timeout* seconds.
            RuntimeError: If the sidecar process has exited.
        """
        with self._lock:
            if self._proc.poll() is not None:
                raise RuntimeError(f"Sidecar process exited with code {self._proc.returncode}")

            line = json.dumps(msg) + "\n"
            assert self._proc.stdin is not None
            assert self._proc.stdout is not None

            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()

            # Read the response line with a timeout using a background thread.
            result: list[bytes | None] = [None]
            error: list[Exception | None] = [None]

            def _read() -> None:
                try:
                    assert self._proc.stdout is not None
                    result[0] = self._proc.stdout.readline()
                except Exception as exc:
                    error[0] = exc

            reader = threading.Thread(target=_read, daemon=True)
            reader.start()
            reader.join(timeout=timeout)

            if reader.is_alive():
                raise TimeoutError(
                    f"Sidecar did not respond within {timeout}s for message type={msg.get('type')}"
                )

            if error[0] is not None:
                raise error[0]

            raw = result[0]
            if not raw:
                raise RuntimeError("Sidecar returned empty response (EOF on stdout)")

            return json.loads(raw.decode("utf-8"))

    def close(self) -> None:
        """Terminate the sidecar process."""
        if self._proc.poll() is None:
            self._proc.stdin.close()  # type: ignore[union-attr]
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)


@pytest.fixture(scope="module")
def sidecar() -> SidecarProcess:
    """Start the Python sidecar subprocess and yield a helper object.

    The fixture is module-scoped so the model is loaded once and shared across
    all tests in this module.
    """
    assert VENV_PYTHON.exists(), (
        f"Virtual-env Python not found at {VENV_PYTHON}. "
        "Create it with: cd backend && python3 -m venv .venv && "
        ".venv/bin/pip install -r requirements.txt"
    )
    assert MAIN_PY.exists(), f"Sidecar entry point not found at {MAIN_PY}"

    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(MAIN_PY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        cwd=str(BACKEND_DIR),
    )

    helper = SidecarProcess(proc)
    yield helper  # type: ignore[misc]
    helper.close()


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify the sidecar responds to health checks."""

    def test_health_check(self, sidecar: SidecarProcess) -> None:
        """Spawn sidecar, send a health message, verify response."""
        resp = sidecar.send_message({"type": "health"}, timeout=10)
        assert resp["type"] == "health"
        assert resp["status"] == "ok"


class TestTranscribeEnglishFull:
    """Send the full English WAV and verify transcription accuracy."""

    def test_transcribe_english_full(self, sidecar: SidecarProcess) -> None:
        """Send entire English WAV as base64 PCM, check key words appear."""
        if not TEST_ENGLISH_WAV.exists():
            pytest.skip(f"Fixture not found: {TEST_ENGLISH_WAV}")

        pcm_bytes, n_channels, sample_width, framerate = _read_wav_pcm(TEST_ENGLISH_WAV)
        audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")

        resp = sidecar.send_message(
            {"type": "transcribe_chunk", "audio_base64": audio_b64},
            timeout=FIRST_TIMEOUT_S,
        )

        assert resp["type"] == "transcription", f"Expected transcription, got: {resp}"
        text = resp["text"]
        assert isinstance(text, str)
        assert len(text) > 0, "Transcription returned empty text"

        # Verify segments structure
        assert "segments" in resp
        assert isinstance(resp["segments"], list)
        assert len(resp["segments"]) > 0

        # Check key words (case-insensitive)
        text_lower = text.lower()
        found = [kw for kw in ENGLISH_KEY_WORDS if kw.lower() in text_lower]
        ratio = len(found) / len(ENGLISH_KEY_WORDS)

        missing = [kw for kw in ENGLISH_KEY_WORDS if kw.lower() not in text_lower]
        assert ratio >= MIN_KEYWORD_RATIO, (
            f"Only {len(found)}/{len(ENGLISH_KEY_WORDS)} key words found "
            f"(need {MIN_KEYWORD_RATIO:.0%}). "
            f"Found: {found}. Missing: {missing}. "
            f"Full text: {text!r}"
        )


class TestTranscribeChineseFull:
    """Send the full Chinese WAV and verify transcription accuracy."""

    def test_transcribe_chinese_full(self, sidecar: SidecarProcess) -> None:
        """Send entire Chinese WAV as base64 PCM, check key Chinese words appear."""
        if not TEST_CHINESE_WAV.exists():
            pytest.skip(f"Fixture not found: {TEST_CHINESE_WAV}")

        pcm_bytes, n_channels, sample_width, framerate = _read_wav_pcm(TEST_CHINESE_WAV)
        audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")

        resp = sidecar.send_message(
            {"type": "transcribe_chunk", "audio_base64": audio_b64},
            timeout=WARM_TIMEOUT_S,
        )

        assert resp["type"] == "transcription", f"Expected transcription, got: {resp}"
        text = resp["text"]
        assert isinstance(text, str)
        assert len(text) > 0, "Transcription returned empty text"

        # Verify segments structure
        assert "segments" in resp
        assert isinstance(resp["segments"], list)
        assert len(resp["segments"]) > 0

        # Check key words (Chinese characters, exact match)
        found = [kw for kw in CHINESE_KEY_WORDS if kw in text]
        ratio = len(found) / len(CHINESE_KEY_WORDS)

        missing = [kw for kw in CHINESE_KEY_WORDS if kw not in text]
        assert ratio >= MIN_KEYWORD_RATIO, (
            f"Only {len(found)}/{len(CHINESE_KEY_WORDS)} key words found "
            f"(need {MIN_KEYWORD_RATIO:.0%}). "
            f"Found: {found}. Missing: {missing}. "
            f"Full text: {text!r}"
        )


class TestTranscribeEnglishChunks:
    """Split English WAV into ~5s chunks and send each as a separate message."""

    def test_transcribe_english_chunks(self, sidecar: SidecarProcess) -> None:
        """Simulate live transcription by sending ~5s PCM chunks sequentially."""
        if not TEST_ENGLISH_WAV.exists():
            pytest.skip(f"Fixture not found: {TEST_ENGLISH_WAV}")

        pcm_bytes, n_channels, sample_width, framerate = _read_wav_pcm(TEST_ENGLISH_WAV)
        chunks = _split_pcm_into_chunks(
            pcm_bytes, sample_width, n_channels, framerate, chunk_duration_s=5.0
        )

        assert len(chunks) >= 2, (
            f"Expected at least 2 chunks for ~22s audio at 5s/chunk, got {len(chunks)}"
        )

        all_texts: list[str] = []

        for i, chunk in enumerate(chunks):
            audio_b64 = base64.b64encode(chunk).decode("ascii")

            resp = sidecar.send_message(
                {"type": "transcribe_chunk", "audio_base64": audio_b64},
                timeout=WARM_TIMEOUT_S,
            )

            assert resp["type"] == "transcription", (
                f"Chunk {i}: expected transcription, got: {resp}"
            )
            chunk_text = resp["text"]
            assert isinstance(chunk_text, str), f"Chunk {i}: text is not a string"

            # Verify response structure
            assert "segments" in resp, f"Chunk {i}: missing 'segments' in response"
            assert isinstance(resp["segments"], list)

            all_texts.append(chunk_text)

        # Combine all chunk transcriptions and check key words
        combined = " ".join(all_texts)
        combined_lower = combined.lower()

        found = [kw for kw in ENGLISH_KEY_WORDS if kw.lower() in combined_lower]
        ratio = len(found) / len(ENGLISH_KEY_WORDS)

        missing = [kw for kw in ENGLISH_KEY_WORDS if kw.lower() not in combined_lower]
        assert ratio >= MIN_KEYWORD_RATIO, (
            f"Chunked transcription: only {len(found)}/{len(ENGLISH_KEY_WORDS)} "
            f"key words found (need {MIN_KEYWORD_RATIO:.0%}). "
            f"Found: {found}. Missing: {missing}. "
            f"Combined text: {combined!r}"
        )


class TestTranscribeChineseChunks:
    """Split Chinese WAV into ~5s chunks and send each as a separate message."""

    def test_transcribe_chinese_chunks(self, sidecar: SidecarProcess) -> None:
        """Simulate live transcription by sending ~5s PCM chunks for Chinese audio."""
        if not TEST_CHINESE_WAV.exists():
            pytest.skip(f"Fixture not found: {TEST_CHINESE_WAV}")

        pcm_bytes, n_channels, sample_width, framerate = _read_wav_pcm(TEST_CHINESE_WAV)
        chunks = _split_pcm_into_chunks(
            pcm_bytes, sample_width, n_channels, framerate, chunk_duration_s=5.0
        )

        assert len(chunks) >= 2, (
            f"Expected at least 2 chunks for ~26s audio at 5s/chunk, got {len(chunks)}"
        )

        all_texts: list[str] = []

        for i, chunk in enumerate(chunks):
            audio_b64 = base64.b64encode(chunk).decode("ascii")

            resp = sidecar.send_message(
                {"type": "transcribe_chunk", "audio_base64": audio_b64},
                timeout=WARM_TIMEOUT_S,
            )

            assert resp["type"] == "transcription", (
                f"Chunk {i}: expected transcription, got: {resp}"
            )
            chunk_text = resp["text"]
            assert isinstance(chunk_text, str), f"Chunk {i}: text is not a string"

            # Verify response structure
            assert "segments" in resp, f"Chunk {i}: missing 'segments' in response"
            assert isinstance(resp["segments"], list)

            all_texts.append(chunk_text)

        # Combine all chunk transcriptions and check key words
        combined = " ".join(all_texts)

        found = [kw for kw in CHINESE_KEY_WORDS if kw in combined]
        ratio = len(found) / len(CHINESE_KEY_WORDS)

        missing = [kw for kw in CHINESE_KEY_WORDS if kw not in combined]
        assert ratio >= MIN_KEYWORD_RATIO, (
            f"Chunked transcription: only {len(found)}/{len(CHINESE_KEY_WORDS)} "
            f"key words found (need {MIN_KEYWORD_RATIO:.0%}). "
            f"Found: {found}. Missing: {missing}. "
            f"Combined text: {combined!r}"
        )


class TestTranscribeWithInitialPrompt:
    """Verify that providing an initial_prompt improves transcription accuracy."""

    def test_transcribe_with_initial_prompt(self, sidecar: SidecarProcess) -> None:
        """Send English audio with an initial_prompt containing expected names/terms.

        The initial_prompt should help Whisper correctly spell proper nouns and
        domain-specific terms that might otherwise be misheard.
        """
        if not TEST_ENGLISH_WAV.exists():
            pytest.skip(f"Fixture not found: {TEST_ENGLISH_WAV}")

        pcm_bytes, n_channels, sample_width, framerate = _read_wav_pcm(TEST_ENGLISH_WAV)
        audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")

        # Send with an initial prompt that hints at expected content
        initial_prompt = (
            "Weekly team meeting with Sarah. "
            "Topics: product launch timeline, engineering budget allocation, "
            "customer feedback review."
        )

        resp = sidecar.send_message(
            {
                "type": "transcribe_chunk",
                "audio_base64": audio_b64,
                "initial_prompt": initial_prompt,
            },
            timeout=WARM_TIMEOUT_S,
        )

        assert resp["type"] == "transcription", f"Expected transcription, got: {resp}"
        text = resp["text"]
        assert isinstance(text, str)
        assert len(text) > 0, "Transcription returned empty text"

        # With the prompt, we expect a higher hit rate on key words
        text_lower = text.lower()
        found = [kw for kw in ENGLISH_KEY_WORDS if kw.lower() in text_lower]
        ratio = len(found) / len(ENGLISH_KEY_WORDS)

        missing = [kw for kw in ENGLISH_KEY_WORDS if kw.lower() not in text_lower]

        # With initial_prompt we expect at least as good as without, ideally better.
        # Use the same threshold but log a note if it's better.
        assert ratio >= MIN_KEYWORD_RATIO, (
            f"With initial_prompt: only {len(found)}/{len(ENGLISH_KEY_WORDS)} "
            f"key words found (need {MIN_KEYWORD_RATIO:.0%}). "
            f"Found: {found}. Missing: {missing}. "
            f"Full text: {text!r}"
        )

        # Specifically check that "Sarah" is found — this proper noun is a good
        # indicator that the initial_prompt is helping.
        assert "sarah" in text_lower, (
            f"Expected 'Sarah' in transcription when initial_prompt mentions her. "
            f"Full text: {text!r}"
        )
