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

    def test_validate_returns_true_for_known_types(self) -> None:
        """Verify that validate returns True for all known MessageType values."""
        for msg_type in MessageType:
            msg = IPCMessage(type=msg_type)
            assert msg.validate() is True

    def test_validate_returns_false_for_unknown_type(self) -> None:
        """Verify that validate returns False for a type not in MessageType."""
        msg = IPCMessage(type="nonexistent_type")
        assert msg.validate() is False

    def test_validate_returns_false_for_default_unknown(self) -> None:
        """Verify that validate returns False for the default 'unknown' type."""
        msg = IPCMessage.from_dict({})
        assert msg.validate() is False


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

    def test_error_creates_error_response(self) -> None:
        """Verify that IPCResponse.error() creates a response with type 'error'."""
        resp = IPCResponse.error("Something went wrong")
        assert resp.type == ResponseType.ERROR
        assert resp.data["message"] == "Something went wrong"

    def test_error_serializes_correctly(self) -> None:
        """Verify that error response serializes to the expected dict shape."""
        d = IPCResponse.error("Bad input").to_dict()
        assert d == {"type": "error", "message": "Bad input"}

    def test_ok_creates_success_response(self) -> None:
        """Verify that IPCResponse.ok() creates a response with the given type."""
        resp = IPCResponse.ok(ResponseType.HEALTH, status="ok")
        assert resp.type == ResponseType.HEALTH
        assert resp.data["status"] == "ok"

    def test_ok_serializes_with_all_data(self) -> None:
        """Verify that ok response includes all keyword arguments in serialization."""
        d = IPCResponse.ok(ResponseType.TRANSCRIPTION, text="hello", is_partial=True).to_dict()
        assert d == {"type": "transcription", "text": "hello", "is_partial": True}


class TestDispatch:
    """Tests for the dispatch function routing messages to handlers."""

    def test_dispatch_routes_health_message(self) -> None:
        """Verify that dispatch routes a health message and returns ok."""
        from main import dispatch

        result = dispatch({"type": "health"})
        assert result["type"] == "health"
        assert result["status"] == "ok"

    def test_dispatch_routes_transcribe_chunk_message(self) -> None:
        """Verify that dispatch routes a transcribe_chunk message correctly."""
        from main import dispatch

        result = dispatch(
            {
                "type": "transcribe_chunk",
                "audio_base64": "dGVzdA==",
                "initial_prompt": "test meeting",
            }
        )
        assert result["type"] == "transcription"

    def test_dispatch_returns_error_for_unknown_type(self) -> None:
        """Verify that dispatch returns an error for an unrecognized message type."""
        from main import dispatch

        result = dispatch({"type": "totally_fake_type"})
        assert result["type"] == "error"
        assert "Unknown message type" in result["message"]
        assert "totally_fake_type" in result["message"]

    def test_dispatch_returns_error_for_missing_type(self) -> None:
        """Verify that dispatch returns an error when the type field is missing."""
        from main import dispatch

        result = dispatch({"data": "no type here"})
        assert result["type"] == "error"

    def test_dispatch_routes_diarize_message(self) -> None:
        """Verify that dispatch routes a diarize message correctly."""
        from main import dispatch

        result = dispatch(
            {
                "type": "diarize",
                "audio_path": "/tmp/test.wav",
                "num_speakers": 2,
            }
        )
        assert result["type"] == "diarization_complete"

    def test_dispatch_routes_identify_speakers_message(self) -> None:
        """Verify that dispatch routes an identify_speakers message correctly."""
        from main import dispatch

        result = dispatch(
            {
                "type": "identify_speakers",
                "embeddings": {"SPEAKER_00": [0.1, 0.2]},
            }
        )
        assert result["type"] == "speaker_match"

    def test_dispatch_routes_summarize_message(self) -> None:
        """Verify that dispatch routes a summarize message correctly."""
        from main import dispatch

        result = dispatch(
            {
                "type": "summarize",
                "transcript": "Alice said hello. Bob said goodbye.",
                "provider": "claude",
                "model": "claude-sonnet-4-5-20250929",
                "api_key": "sk-test-key",
            }
        )
        assert result["type"] == "summary_complete"


class TestHandlers:
    """Tests for individual handler functions and their field validation."""

    def test_handle_transcribe_chunk_validates_audio_base64(self) -> None:
        """Verify that handle_transcribe_chunk returns error when audio_base64 is missing."""
        from ipc.handlers import handle_transcribe_chunk

        msg = IPCMessage(type=MessageType.TRANSCRIBE_CHUNK, payload={})
        resp = handle_transcribe_chunk(msg)
        assert resp.type == ResponseType.ERROR
        assert "audio_base64" in resp.data["message"]

    def test_handle_transcribe_chunk_succeeds_with_required_fields(self) -> None:
        """Verify handle_transcribe_chunk returns transcription with audio_base64."""
        from ipc.handlers import handle_transcribe_chunk

        msg = IPCMessage(
            type=MessageType.TRANSCRIBE_CHUNK,
            payload={"audio_base64": "dGVzdA=="},
        )
        resp = handle_transcribe_chunk(msg)
        assert resp.type == ResponseType.TRANSCRIPTION

    def test_handle_diarize_validates_audio_path(self) -> None:
        """Verify that handle_diarize returns error when audio_path is missing."""
        from ipc.handlers import handle_diarize

        msg = IPCMessage(type=MessageType.DIARIZE, payload={})
        resp = handle_diarize(msg)
        assert resp.type == ResponseType.ERROR
        assert "audio_path" in resp.data["message"]

    def test_handle_diarize_succeeds_with_required_fields(self) -> None:
        """Verify that handle_diarize returns diarization result when audio_path is present."""
        from ipc.handlers import handle_diarize

        msg = IPCMessage(
            type=MessageType.DIARIZE,
            payload={"audio_path": "/tmp/test.wav"},
        )
        resp = handle_diarize(msg)
        assert resp.type == ResponseType.DIARIZATION_COMPLETE

    def test_handle_identify_speakers_validates_embeddings(self) -> None:
        """Verify that handle_identify_speakers returns error when embeddings is missing."""
        from ipc.handlers import handle_identify_speakers

        msg = IPCMessage(type=MessageType.IDENTIFY_SPEAKERS, payload={})
        resp = handle_identify_speakers(msg)
        assert resp.type == ResponseType.ERROR
        assert "embeddings" in resp.data["message"]

    def test_handle_identify_speakers_succeeds_with_required_fields(self) -> None:
        """Verify that handle_identify_speakers returns matches when embeddings are present."""
        from ipc.handlers import handle_identify_speakers

        msg = IPCMessage(
            type=MessageType.IDENTIFY_SPEAKERS,
            payload={"embeddings": {"SPEAKER_00": [0.1, 0.2]}},
        )
        resp = handle_identify_speakers(msg)
        assert resp.type == ResponseType.SPEAKER_MATCH

    def test_handle_summarize_validates_transcript(self) -> None:
        """Verify that handle_summarize returns error when transcript is missing."""
        from ipc.handlers import handle_summarize

        msg = IPCMessage(
            type=MessageType.SUMMARIZE,
            payload={
                "provider": "claude",
                "model": "claude-sonnet-4-5-20250929",
                "api_key": "sk-test",
            },
        )
        resp = handle_summarize(msg)
        assert resp.type == ResponseType.ERROR
        assert "transcript" in resp.data["message"]

    def test_handle_summarize_validates_provider(self) -> None:
        """Verify that handle_summarize returns error when provider is missing."""
        from ipc.handlers import handle_summarize

        msg = IPCMessage(
            type=MessageType.SUMMARIZE,
            payload={"transcript": "hello", "model": "gpt-4", "api_key": "sk-test"},
        )
        resp = handle_summarize(msg)
        assert resp.type == ResponseType.ERROR
        assert "provider" in resp.data["message"]

    def test_handle_summarize_validates_model(self) -> None:
        """Verify that handle_summarize returns error when model is missing."""
        from ipc.handlers import handle_summarize

        msg = IPCMessage(
            type=MessageType.SUMMARIZE,
            payload={"transcript": "hello", "provider": "claude", "api_key": "sk-test"},
        )
        resp = handle_summarize(msg)
        assert resp.type == ResponseType.ERROR
        assert "model" in resp.data["message"]

    def test_handle_summarize_validates_api_key(self) -> None:
        """Verify that handle_summarize returns error when api_key is missing."""
        from ipc.handlers import handle_summarize

        msg = IPCMessage(
            type=MessageType.SUMMARIZE,
            payload={"transcript": "hello", "provider": "claude", "model": "gpt-4"},
        )
        resp = handle_summarize(msg)
        assert resp.type == ResponseType.ERROR
        assert "api_key" in resp.data["message"]

    def test_handle_summarize_succeeds_with_all_required_fields(self) -> None:
        """Verify that handle_summarize returns summary when all required fields are present."""
        from ipc.handlers import handle_summarize

        msg = IPCMessage(
            type=MessageType.SUMMARIZE,
            payload={
                "transcript": "Alice said hello.",
                "provider": "claude",
                "model": "claude-sonnet-4-5-20250929",
                "api_key": "sk-test-key",
            },
        )
        resp = handle_summarize(msg)
        assert resp.type == ResponseType.SUMMARY_COMPLETE

    def test_handle_health_returns_ok(self) -> None:
        """Verify that handle_health returns a health ok response."""
        from ipc.handlers import handle_health

        msg = IPCMessage(type=MessageType.HEALTH)
        resp = handle_health(msg)
        assert resp.type == ResponseType.HEALTH
        assert resp.data["status"] == "ok"


class TestRoundTrip:
    """Tests for full round-trip: dict -> IPCMessage -> handler -> IPCResponse -> dict."""

    def test_health_round_trip(self) -> None:
        """Verify full round-trip for a health message."""
        raw = {"type": "health"}
        msg = IPCMessage.from_dict(raw)
        assert msg.validate() is True

        from ipc.handlers import handle_health

        resp = handle_health(msg)
        result = resp.to_dict()
        assert result == {"type": "health", "status": "ok"}

    def test_transcribe_chunk_round_trip(self) -> None:
        """Verify full round-trip for a transcribe_chunk message."""
        raw = {"type": "transcribe_chunk", "audio_base64": "dGVzdA=="}
        msg = IPCMessage.from_dict(raw)
        assert msg.validate() is True

        from ipc.handlers import handle_transcribe_chunk

        resp = handle_transcribe_chunk(msg)
        result = resp.to_dict()
        assert result["type"] == "transcription"
        assert "text" in result

    def test_error_round_trip_for_invalid_message(self) -> None:
        """Verify full round-trip for an invalid message type produces error dict."""
        raw = {"type": "bogus"}
        msg = IPCMessage.from_dict(raw)
        assert msg.validate() is False

        resp = IPCResponse.error(f"Unknown message type: {msg.type}")
        result = resp.to_dict()
        assert result["type"] == "error"
        assert "bogus" in result["message"]
