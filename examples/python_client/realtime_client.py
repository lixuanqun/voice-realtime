"""Minimal OpenAI Realtime client for a local voice-realtime gateway."""

from __future__ import annotations

import argparse
import base64
import json
from contextlib import closing
from pathlib import Path
from typing import Any

import websocket

UNSUCCESSFUL_RESPONSE_STATUSES = {"cancelled", "failed", "incomplete"}


def send_event(connection: websocket.WebSocket, event: dict[str, Any]) -> None:
    """Send one OpenAI Realtime JSON event."""
    connection.send(json.dumps(event))


def append_audio(connection: websocket.WebSocket, audio_path: Path) -> None:
    """Send raw PCM16 audio as input_audio_buffer.append events."""
    audio = audio_path.read_bytes()
    # Leave room for base64 and JSON within the gateway's 32 KiB read limit.
    chunk_size = 18_000
    for offset in range(0, len(audio), chunk_size):
        encoded = base64.b64encode(audio[offset : offset + chunk_size]).decode("ascii")
        send_event(
            connection,
            {
                "type": "input_audio_buffer.append",
                "audio": encoded,
            },
        )


def receive_response(connection: websocket.WebSocket, output_path: Path) -> None:
    """Print gateway events and save response.audio.delta PCM16 audio."""
    output = bytearray()
    while True:
        raw_event = connection.recv()
        if not isinstance(raw_event, str):
            continue

        event = json.loads(raw_event)
        event_type = event.get("type", "unknown")
        print(f"Received: {event_type}")

        if event_type == "response.audio.delta":
            output.extend(base64.b64decode(event.get("delta", "")))
        elif event_type == "error":
            raise RuntimeError(
                event.get("error", {}).get("message", "Gateway returned an error")
            )
        elif event_type == "response.done":
            response = event.get("response", {})
            status = response.get("status")
            if status in UNSUCCESSFUL_RESPONSE_STATUSES:
                status_details = response.get("status_details")
                details = (
                    json.dumps(status_details, ensure_ascii=False)
                    if status_details is not None
                    else "no status details"
                )
                raise RuntimeError(f"Response ended with status {status}: {details}")
            break

    if output:
        output_path.write_bytes(output)
        print(f"Saved {len(output)} bytes of PCM16 audio to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="ws://localhost:8080/v1/realtime?provider=zhipu&model=glm-realtime-flash",
        help="voice-realtime WebSocket URL",
    )
    parser.add_argument(
        "--audio", type=Path, help="Optional 24 kHz mono PCM16 input file"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("response.pcm"), help="PCM16 output path"
    )
    args = parser.parse_args()

    with closing(websocket.create_connection(args.url, timeout=30)) as connection:
        send_event(
            connection,
            {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": "Reply briefly in Mandarin.",
                },
            },
        )

        if args.audio:
            append_audio(connection, args.audio)
            send_event(connection, {"type": "input_audio_buffer.commit"})

        send_event(
            connection,
            {
                "type": "response.create",
                "response": {"modalities": ["text", "audio"]},
            },
        )
        receive_response(connection, args.output)


if __name__ == "__main__":
    main()
