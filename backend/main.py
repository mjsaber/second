"""Main entry point for the Second Python sidecar.

Communicates with the Electron main process via a JSON-over-stdin/stdout protocol.
Each line on stdin is a JSON message; each response is a JSON line on stdout.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    """Main entry point for the Python sidecar. Reads JSON from stdin, dispatches to handlers."""
    for line in sys.stdin:
        try:
            message = json.loads(line.strip())
            response = dispatch(message)
            print(json.dumps(response), flush=True)
        except Exception as e:
            error_response: dict[str, str] = {"type": "error", "message": str(e)}
            print(json.dumps(error_response), flush=True)


def dispatch(message: dict[str, object]) -> dict[str, object]:
    """Route messages to appropriate handlers.

    Args:
        message: Parsed JSON message with at least a 'type' field.

    Returns:
        Response dictionary to be serialized as JSON.
    """
    msg_type = message.get("type")

    # Stub — will be implemented with real handlers for:
    #   - "transcribe": start/stop transcription
    #   - "summarize": generate meeting summary
    #   - "identify_speaker": match speaker embedding
    #   - "query_db": database operations
    #   - "health": health check
    if msg_type == "health":
        return {"type": "health", "status": "ok"}

    return {"type": "error", "message": f"Unknown message type: {msg_type}"}


if __name__ == "__main__":
    main()
