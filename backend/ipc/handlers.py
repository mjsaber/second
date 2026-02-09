"""Handler functions for each IPC message type.

Each handler receives an IPCMessage and returns an IPCResponse.
Handlers are pure functions — they validate input and return response stubs.
"""

from __future__ import annotations

from collections.abc import Callable

from ipc.protocol import IPCMessage, IPCResponse, MessageType, ResponseType


def handle_health(msg: IPCMessage) -> IPCResponse:
    """Handle a health check message."""
    return IPCResponse.ok(ResponseType.HEALTH, status="ok")


def handle_transcribe_chunk(msg: IPCMessage) -> IPCResponse:
    """Handle a transcribe_chunk message.

    Base64-decodes the audio payload and returns the transcription response structure.
    Actual transcription is not yet wired up — this is a stub that returns the proper format.

    Required payload fields: audio_base64.
    """
    if "audio_base64" not in msg.payload:
        return IPCResponse.error(
            "Missing required field 'audio_base64' in transcribe_chunk message"
        )
    # Decode the base64 audio (validates the encoding; actual transcription is a stub)
    import base64

    base64.b64decode(msg.payload["audio_base64"])

    return IPCResponse.ok(ResponseType.TRANSCRIPTION, text="", segments=[], is_partial=False)


def handle_diarize(msg: IPCMessage) -> IPCResponse:
    """Handle a diarize message.

    Runs the pyannote diarization pipeline on the given audio file and returns
    speaker segments with per-speaker embeddings.

    Required payload fields: audio_path.
    Optional payload fields: num_speakers.
    """
    if "audio_path" not in msg.payload:
        return IPCResponse.error("Missing required field 'audio_path' in diarize message")

    audio_path: str = msg.payload["audio_path"]
    # Validate audio file has a recognized extension
    valid_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    from pathlib import Path as _Path

    if _Path(audio_path).suffix.lower() not in valid_extensions:
        return IPCResponse.error(
            f"Invalid audio file extension: {_Path(audio_path).suffix!r}. "
            f"Expected one of: {', '.join(sorted(valid_extensions))}"
        )
    num_speakers: int | None = msg.payload.get("num_speakers")

    try:
        from diarization.pipeline import DiarizationPipeline

        pipeline = DiarizationPipeline()
        pipeline.load()
        result = pipeline.diarize(audio_path, num_speakers=num_speakers)
        embeddings = pipeline.extract_embeddings(audio_path, result.segments)

        segments_data = [
            {"speaker": seg.speaker, "start": seg.start, "end": seg.end} for seg in result.segments
        ]

        return IPCResponse.ok(
            ResponseType.DIARIZATION_COMPLETE,
            segments=segments_data,
            embeddings=embeddings,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        return IPCResponse.error(str(exc))


def handle_identify_speakers(msg: IPCMessage) -> IPCResponse:
    """Handle an identify_speakers message.

    Required payload fields: embeddings.
    Optional payload fields: known_embeddings.
    """
    if "embeddings" not in msg.payload:
        return IPCResponse.error("Missing required field 'embeddings' in identify_speakers message")

    from speaker_id.identifier import SpeakerIdentifier

    embeddings: dict[str, list[float]] = msg.payload["embeddings"]
    known_embeddings: dict[str, list[float]] | None = msg.payload.get("known_embeddings")

    identifier = SpeakerIdentifier()
    matches = identifier.identify(embeddings, known_embeddings=known_embeddings)

    matches_data = [
        {
            "speaker_label": m.speaker_label,
            "matched_name": m.matched_name,
            "confidence": m.confidence,
        }
        for m in matches
    ]

    return IPCResponse.ok(ResponseType.SPEAKER_MATCH, matches=matches_data)


def handle_summarize(msg: IPCMessage) -> IPCResponse:
    """Handle a summarize message.

    Required payload fields: transcript, provider, model, api_key.
    """
    required_fields = ("transcript", "provider", "model", "api_key")
    for field in required_fields:
        if field not in msg.payload:
            return IPCResponse.error(f"Missing required field '{field}' in summarize message")

    from summarization.providers import (
        LLMProvider,
        SummarizationRequest,
        SummarizationService,
    )

    service = SummarizationService()
    request = SummarizationRequest(
        transcript=msg.payload["transcript"],
        provider=LLMProvider(msg.payload["provider"]),
        model=msg.payload["model"],
        api_key=msg.payload.get("api_key"),
    )

    try:
        result = service.summarize(request)
    except (ValueError, ConnectionError, RuntimeError) as e:
        return IPCResponse.error(str(e))

    return IPCResponse.ok(
        ResponseType.SUMMARY_COMPLETE,
        markdown=result.markdown,
        provider=result.provider.value,
        model=result.model,
        token_count=result.token_count,
    )


HANDLER_MAP: dict[str, Callable[[IPCMessage], IPCResponse]] = {
    MessageType.HEALTH: handle_health,
    MessageType.TRANSCRIBE_CHUNK: handle_transcribe_chunk,
    MessageType.DIARIZE: handle_diarize,
    MessageType.IDENTIFY_SPEAKERS: handle_identify_speakers,
    MessageType.SUMMARIZE: handle_summarize,
}
