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

    Required payload fields: audio_base64.
    """
    if "audio_base64" not in msg.payload:
        return IPCResponse.error(
            "Missing required field 'audio_base64' in transcribe_chunk message"
        )
    return IPCResponse.ok(ResponseType.TRANSCRIPTION, text="", is_partial=False)


def handle_diarize(msg: IPCMessage) -> IPCResponse:
    """Handle a diarize message.

    Required payload fields: audio_path.
    """
    if "audio_path" not in msg.payload:
        return IPCResponse.error("Missing required field 'audio_path' in diarize message")
    return IPCResponse.ok(ResponseType.DIARIZATION_COMPLETE, segments=[], embeddings={})


def handle_identify_speakers(msg: IPCMessage) -> IPCResponse:
    """Handle an identify_speakers message.

    Required payload fields: embeddings.
    """
    if "embeddings" not in msg.payload:
        return IPCResponse.error("Missing required field 'embeddings' in identify_speakers message")
    return IPCResponse.ok(ResponseType.SPEAKER_MATCH, matches={})


def handle_summarize(msg: IPCMessage) -> IPCResponse:
    """Handle a summarize message.

    Required payload fields: transcript, provider, model, api_key.
    """
    required_fields = ("transcript", "provider", "model", "api_key")
    for field in required_fields:
        if field not in msg.payload:
            return IPCResponse.error(f"Missing required field '{field}' in summarize message")
    return IPCResponse.ok(ResponseType.SUMMARY_COMPLETE, markdown="")


HANDLER_MAP: dict[str, Callable[[IPCMessage], IPCResponse]] = {
    MessageType.HEALTH: handle_health,
    MessageType.TRANSCRIBE_CHUNK: handle_transcribe_chunk,
    MessageType.DIARIZE: handle_diarize,
    MessageType.IDENTIFY_SPEAKERS: handle_identify_speakers,
    MessageType.SUMMARIZE: handle_summarize,
}
