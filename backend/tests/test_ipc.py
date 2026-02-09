"""Tests for the IPC protocol module."""

from __future__ import annotations

from ipc.protocol import IPCMessage, IPCResponse, MessageType, ResponseType


class TestIPCMessage:
    """Tests for IPCMessage parsing and construction."""

    def test_from_dict_parses_type(self) -> None:
        """Verify that from_dict correctly extracts the message type."""
        raw = {"type": "health", "extra": "data"}
        msg = IPCMessage.from_dict(raw)
        assert msg.type == "health"
        assert msg.payload == {"extra": "data"}

    def test_from_dict_missing_type_defaults_to_unknown(self) -> None:
        """Verify that a message without a type field gets 'unknown'."""
        msg = IPCMessage.from_dict({})
        assert msg.type == "unknown"

    def test_message_types_are_strings(self) -> None:
        """Verify that MessageType enum values are usable as strings."""
        assert MessageType.HEALTH == "health"
        assert MessageType.TRANSCRIBE_CHUNK == "transcribe_chunk"


class TestIPCResponse:
    """Tests for IPCResponse serialization."""

    def test_to_dict_includes_type(self) -> None:
        """Verify that to_dict includes the type field."""
        resp = IPCResponse(type="health", data={"status": "ok"})
        d = resp.to_dict()
        assert d["type"] == "health"
        assert d["status"] == "ok"

    def test_response_types_are_strings(self) -> None:
        """Verify that ResponseType enum values are usable as strings."""
        assert ResponseType.ERROR == "error"
        assert ResponseType.SUMMARY_COMPLETE == "summary_complete"
