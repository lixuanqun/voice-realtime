"""Tests for the minimal OpenAI Realtime client."""

from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from examples.python_client import realtime_client


class MockTransport:
    """A closeable transport, deliberately not a context manager."""

    def __init__(self, events: list[dict[str, object] | Exception]) -> None:
        self.events = iter(events)
        self.sent: list[str] = []
        self.closed = False

    def send(self, data: str) -> None:
        self.sent.append(data)

    def recv(self) -> str:
        event = next(self.events)
        if isinstance(event, Exception):
            raise event
        return json.dumps(event)

    def close(self) -> None:
        self.closed = True


class ClientTestCase(unittest.TestCase):
    def setUp(self) -> None:
        stdout = patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = stdout.start()
        self.addCleanup(stdout.stop)


class ReceiveResponseTest(ClientTestCase):
    def test_saves_audio_after_successful_response(self) -> None:
        for response in ({"status": "completed"}, {}):
            with (
                self.subTest(response=response),
                tempfile.TemporaryDirectory() as directory,
            ):
                output_path = Path(directory) / "response.pcm"
                transport = MockTransport(
                    [
                        {
                            "type": "response.audio.delta",
                            "delta": base64.b64encode(b"complete audio").decode(
                                "ascii"
                            ),
                        },
                        {"type": "response.done", "response": response},
                    ]
                )

                realtime_client.receive_response(  # type: ignore[arg-type]
                    transport,
                    output_path,
                )

                self.assertEqual(output_path.read_bytes(), b"complete audio")

    def test_does_not_save_partial_audio_for_unsuccessful_response(self) -> None:
        cases = {
            "cancelled": {"type": "cancelled", "reason": "turn_detected"},
            "failed": {
                "type": "failed",
                "error": {
                    "type": "server_error",
                    "code": "provider_failed",
                    "message": "provider rejected request",
                },
            },
            "incomplete": {"type": "incomplete", "reason": "max_output_tokens"},
        }

        for status, status_details in cases.items():
            with (
                self.subTest(status=status),
                tempfile.TemporaryDirectory() as directory,
            ):
                output_path = Path(directory) / "response.pcm"
                transport = MockTransport(
                    [
                        {
                            "type": "response.audio.delta",
                            "delta": base64.b64encode(b"partial audio").decode("ascii"),
                        },
                        {
                            "type": "response.done",
                            "response": {
                                "status": status,
                                "status_details": status_details,
                            },
                        },
                    ]
                )

                with self.assertRaisesRegex(
                    RuntimeError,
                    f"Response ended with status {status}",
                ) as error:
                    realtime_client.receive_response(  # type: ignore[arg-type]
                        transport,
                        output_path,
                    )

                self.assertIn(json.dumps(status_details), str(error.exception))
                self.assertFalse(output_path.exists())

    def test_ignores_audio_delta_without_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "response.pcm"
            transport = MockTransport(
                [
                    {"type": "response.audio.delta"},
                    {
                        "type": "response.audio.delta",
                        "delta": base64.b64encode(b"valid audio").decode("ascii"),
                    },
                    {"type": "response.done"},
                ]
            )

            realtime_client.receive_response(transport, output_path)  # type: ignore[arg-type]

            self.assertEqual(output_path.read_bytes(), b"valid audio")

    def test_gateway_error_does_not_overwrite_existing_output(self) -> None:
        for event, message in (
            (
                {"type": "error", "error": {"message": "provider rejected request"}},
                "provider rejected request",
            ),
            ({"type": "error"}, "Gateway returned an error"),
        ):
            with self.subTest(event=event), tempfile.TemporaryDirectory() as directory:
                output_path = Path(directory) / "response.pcm"
                output_path.write_bytes(b"previous recording")
                transport = MockTransport(
                    [
                        {
                            "type": "response.audio.delta",
                            "delta": base64.b64encode(b"partial audio").decode("ascii"),
                        },
                        event,
                    ]
                )

                with self.assertRaisesRegex(RuntimeError, message):
                    realtime_client.receive_response(transport, output_path)  # type: ignore[arg-type]

                self.assertEqual(output_path.read_bytes(), b"previous recording")


class AppendAudioTest(ClientTestCase):
    def test_chunks_fit_gateway_read_limit_and_preserve_audio(self) -> None:
        for size in (0, 2, 17_998, 18_000, 18_002, 54_000, 60_000):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as directory:
                audio = (bytes(range(256)) * (size // 256 + 1))[:size]
                audio_path = Path(directory) / "input.pcm"
                audio_path.write_bytes(audio)
                transport = MockTransport([])

                realtime_client.append_audio(transport, audio_path)  # type: ignore[arg-type]

                self.assertEqual(len(transport.sent), (size + 17_999) // 18_000)
                decoded = bytearray()
                for message in transport.sent:
                    self.assertLessEqual(len(message.encode("utf-8")), 32_768)
                    event = json.loads(message)
                    self.assertEqual(event["type"], "input_audio_buffer.append")
                    chunk = base64.b64decode(event["audio"], validate=True)
                    self.assertLessEqual(len(chunk), 18_000)
                    self.assertEqual(len(chunk) % 2, 0)
                    decoded.extend(chunk)
                self.assertEqual(decoded, audio)


class MainTest(ClientTestCase):
    def run_client(self, transport: MockTransport, arguments: list[str]) -> None:
        url = "ws://localhost:8080/v1/realtime?provider=zhipu"
        with (
            patch("sys.argv", ["realtime_client.py", "--url", url, *arguments]),
            patch.object(
                realtime_client.websocket, "create_connection", return_value=transport
            ) as connect,
        ):
            self.addCleanup(connect.assert_called_once_with, url, timeout=30)
            realtime_client.main()

    def test_starts_without_audio_and_closes_connection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "response.pcm"
            transport = MockTransport([{"type": "response.done"}])

            self.run_client(transport, ["--output", str(output_path)])

            self.assertEqual(
                [json.loads(message)["type"] for message in transport.sent],
                ["session.update", "response.create"],
            )
            self.assertTrue(transport.closed)
            self.assertFalse(output_path.exists())

    def test_uploads_audio_in_order_and_reassembles_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "input.pcm"
            audio_path.write_bytes(b"\x00\x01" * 30_000)
            output_path = Path(directory) / "response.pcm"
            transport = MockTransport(
                [
                    {"type": "session.updated"},
                    {"type": "response.audio.delta", "delta": "AAE="},
                    {"type": "response.audio.delta", "delta": "AgM="},
                    {"type": "response.done", "response": {"status": "completed"}},
                ]
            )

            self.run_client(
                transport, ["--audio", str(audio_path), "--output", str(output_path)]
            )

            events = [json.loads(message) for message in transport.sent]
            self.assertEqual(
                [event["type"] for event in events],
                ["session.update"]
                + ["input_audio_buffer.append"] * 4
                + ["input_audio_buffer.commit", "response.create"],
            )
            self.assertEqual(
                b"".join(base64.b64decode(event["audio"]) for event in events[1:5]),
                audio_path.read_bytes(),
            )
            self.assertEqual(output_path.read_bytes(), b"\x00\x01\x02\x03")
            self.assertTrue(transport.closed)

    def test_closes_connection_on_response_error_or_timeout(self) -> None:
        cases = [
            ({"type": "error", "error": {"message": "gateway failed"}}, RuntimeError),
            (
                {"type": "response.done", "response": {"status": "cancelled"}},
                RuntimeError,
            ),
            (
                realtime_client.websocket.WebSocketTimeoutException("timed out"),
                realtime_client.websocket.WebSocketTimeoutException,
            ),
        ]
        for event, error_type in cases:
            with self.subTest(event=event), tempfile.TemporaryDirectory() as directory:
                output_path = Path(directory) / "response.pcm"
                transport = MockTransport(
                    [{"type": "response.audio.delta", "delta": "AAE="}, event]
                )

                with self.assertRaises(error_type):
                    self.run_client(transport, ["--output", str(output_path)])

                self.assertTrue(transport.closed)
                self.assertFalse(output_path.exists())

    def test_closes_connection_when_input_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = MockTransport([])

            with self.assertRaises(FileNotFoundError):
                self.run_client(
                    transport, ["--audio", str(Path(directory) / "missing.pcm")]
                )

            self.assertTrue(transport.closed)


if __name__ == "__main__":
    unittest.main()
