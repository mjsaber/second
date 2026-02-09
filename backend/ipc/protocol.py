"""JSON message protocol for the stdin/stdout IPC bridge.

Defines the message types exchanged between the Rust/Tauri host process
and this Python sidecar. All messages are single-line JSON terminated by newline.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    """All recognized inbound message types from the host process."""

    TRANSCRIBE_CHUNK = "transcribe_chunk"
    DIARIZE = "diarize"
    IDENTIFY_SPEAKERS = "identify_speakers"
    SUMMARIZE = "summarize"
    HEALTH = "health"


class ResponseType(StrEnum):
    """All outbound response types sent back to the host process."""

    TRANSCRIPTION = "transcription"
    DIARIZATION_COMPLETE = "diarization_complete"
    SPEAKER_MATCH = "speaker_match"
    SUMMARY_COMPLETE = "summary_complete"
    HEALTH = "health"
    ERROR = "error"


class IPCMessage:
    """Represents an inbound message from the host process.

    Attributes:
        type: The message type identifier.
        payload: Arbitrary message data.
    """

    def __init__(self, type: str, payload: dict[str, Any] | None = None) -> None:
        self.type = type
        self.payload = payload or {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCMessage:
        """Parse a raw dictionary into an IPCMessage."""
        msg_type = data.get("type", "unknown")
        payload = {k: v for k, v in data.items() if k != "type"}
        return cls(type=msg_type, payload=payload)


class IPCResponse:
    """Represents an outbound response to the host process.

    Attributes:
        type: The response type identifier.
        data: Response payload.
    """

    def __init__(self, type: str, data: dict[str, Any] | None = None) -> None:
        self.type = type
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary suitable for JSON encoding."""
        return {"type": self.type, **self.data}
