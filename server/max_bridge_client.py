from __future__ import annotations

import json
import os
import socket
from typing import Any, Optional


DEFAULT_HOST = os.environ.get("AIRA_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("AIRA_MCP_PORT", "37820"))
DEFAULT_TIMEOUT = 60.0


class MaxBridgeError(RuntimeError):
    pass


def send_bridge_command(
    command: str,
    host: Optional[str] = None,
    port: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Send one whitelisted command to the 3ds Max bridge."""

    command = command.strip()
    if not command:
        raise MaxBridgeError("Bridge command cannot be empty.")

    host = host or os.environ.get("AIRA_MCP_HOST", DEFAULT_HOST)
    port = int(port or os.environ.get("AIRA_MCP_PORT", DEFAULT_PORT))

    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall((command + "\n").encode("utf-8"))
            with sock.makefile("r", encoding="utf-8", newline="\n") as reader:
                line = reader.readline()
    except OSError as exc:
        raise MaxBridgeError(
            f"Could not connect to 3ds Max bridge at {host}:{port}. "
            "Run maxscript/aira_mcp_bridge.ms inside 3ds Max first."
        ) from exc

    if not line:
        raise MaxBridgeError("3ds Max bridge returned an empty response.")

    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MaxBridgeError(f"Invalid bridge response: {line!r}") from exc

    return payload
