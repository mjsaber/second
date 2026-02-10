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
    SAVE_SUMMARY = "save_summary"
    GET_ALL_SPEAKERS = "get_all_speakers"
    GET_SUMMARIES_FOR_SPEAKER = "get_summaries_for_speaker"
    GET_SUMMARY_DETAIL = "get_summary_detail"
    SEARCH_SUMMARIES = "search_summaries"
    SAVE_SETTINGS = "save_settings"
    LOAD_SETTINGS = "load_settings"


class ResponseType(StrEnum):
    """All outbound response types sent back to the host process."""

    TRANSCRIPTION = "transcription"
    DIARIZATION_COMPLETE = "diarization_complete"
    SPEAKER_MATCH = "speaker_match"
    SUMMARY_COMPLETE = "summary_complete"
    HEALTH = "health"
    ERROR = "error"
    SUMMARY_SAVED = "summary_saved"
    SPEAKERS_LIST = "speakers_list"
    SUMMARIES_LIST = "summaries_list"
    SUMMARY_DETAIL = "summary_detail"
    SEARCH_RESULTS = "search_results"
    SETTINGS_SAVED = "settings_saved"
    SETTINGS_LOADED = "settings_loaded"


_KNOWN_MESSAGE_TYPES: set[str] = {member.value for member in MessageType}


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

    def validate(self) -> bool:
        """Check that the message type is a known MessageType."""
        return self.type in _KNOWN_MESSAGE_TYPES


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

    @classmethod
    def error(cls, message: str) -> IPCResponse:
        """Create an error response quickly.

        Args:
            message: Human-readable error description.
        """
        return cls(type=ResponseType.ERROR, data={"message": message})

    @classmethod
    def ok(cls, type: str, **data: Any) -> IPCResponse:
        """Create a success response.

        Args:
            type: The response type identifier.
            **data: Arbitrary response payload fields.
        """
        return cls(type=type, data=data)
