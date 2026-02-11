"""Main entry point for the Second Python sidecar.

Communicates with the Tauri host process via a JSON-over-stdin/stdout protocol.
Each line on stdin is a JSON message; each response is a JSON line on stdout.
"""

from __future__ import annotations

import json
import sys

from ipc.handlers import HANDLER_MAP
from ipc.protocol import IPCMessage, IPCResponse


def main() -> None:
    """Read JSON lines from stdin, dispatch to handlers, write JSON responses to stdout."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break  # EOF — host process closed stdin
        try:
            message = json.loads(line.strip())
            response = dispatch(message)
            print(json.dumps(response), flush=True)
        except Exception as e:
            error_response = IPCResponse.error(str(e)).to_dict()
            print(json.dumps(error_response), flush=True)


def dispatch(message: dict[str, object]) -> dict[str, object]:
    """Route a raw message dict to the appropriate handler.

    Args:
        message: Parsed JSON message with at least a 'type' field.

    Returns:
        Response dictionary to be serialized as JSON.
    """
    msg = IPCMessage.from_dict(message)  # type: ignore[arg-type]

    if not msg.validate():
        return IPCResponse.error(f"Unknown message type: {msg.type}").to_dict()

    handler = HANDLER_MAP.get(msg.type)
    if handler is None:
        return IPCResponse.error(f"No handler registered for message type: {msg.type}").to_dict()

    response = handler(msg)
    return response.to_dict()


if __name__ == "__main__":
    main()
