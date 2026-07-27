from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from core.tos_public_storage import PublicTOSObject, PublicTOSStorage, TOSStorageError


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True


class TOSPublicStorageTests(unittest.TestCase):
    @patch("core.tos_public_storage.uuid.uuid4")
    @patch("core.tos_public_storage.requests.put")
    def test_upload_streams_original_file_and_preserves_suffix(self, put, uuid4) -> None:
        uuid4.return_value.hex = "a" * 32
        captured = b""

        def upload(_url, *, data, **_kwargs):
            nonlocal captured
            captured = data.read()
            return FakeResponse(200)

        put.side_effect = upload
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "speech.m4a"
            source.write_bytes(b"original-audio")
            storage = PublicTOSStorage()

            uploaded = storage.upload(
                source,
                suffix=".m4a",
                content_type="audio/mp4",
                stopped=lambda: False,
            )

        self.assertEqual(captured, b"original-audio")
        self.assertTrue(uploaded.key.endswith(f"{'a' * 32}.m4a"))
        self.assertTrue(uploaded.url.endswith(f"{'a' * 32}.m4a"))
        self.assertEqual(put.call_args.kwargs["headers"]["Content-Type"], "audio/mp4")
        self.assertEqual(put.call_args.kwargs["headers"]["Content-Length"], str(len(captured)))

    @patch("core.tos_public_storage._wait_or_stop")
    @patch("core.tos_public_storage.requests.put")
    def test_upload_retries_transient_network_failure(self, put, wait) -> None:
        put.side_effect = [requests.ConnectionError("reset"), FakeResponse(200)]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "speech.mp3"
            source.write_bytes(b"audio")

            uploaded = PublicTOSStorage().upload(
                source,
                suffix=".mp3",
                content_type="audio/mpeg",
                stopped=lambda: False,
            )

        self.assertIsInstance(uploaded, PublicTOSObject)
        self.assertEqual(put.call_count, 2)
        wait.assert_called_once()

    @patch("core.tos_public_storage.requests.put")
    def test_upload_stops_before_network_request(self, put) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "speech.mp3"
            source.write_bytes(b"audio")

            with self.assertRaisesRegex(TOSStorageError, "已停止"):
                PublicTOSStorage().upload(
                    source,
                    suffix=".mp3",
                    content_type="audio/mpeg",
                    stopped=lambda: True,
                )

        put.assert_not_called()

    @patch.object(PublicTOSStorage, "delete", return_value=True)
    @patch("core.tos_public_storage.requests.put")
    def test_upload_stops_while_streaming_and_cleans_object(self, put, delete) -> None:
        stop_event = threading.Event()

        def upload(_url, *, data, **_kwargs):
            data.read(2)
            stop_event.set()
            data.read(2)
            return FakeResponse(200)

        put.side_effect = upload
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "speech.mp3"
            source.write_bytes(b"audio")

            with self.assertRaisesRegex(TOSStorageError, "已停止"):
                PublicTOSStorage().upload(
                    source,
                    suffix=".mp3",
                    content_type="audio/mpeg",
                    stopped=stop_event.is_set,
                )

        delete.assert_called_once()

    @patch("core.tos_public_storage.time.sleep")
    @patch("core.tos_public_storage.requests.delete")
    def test_delete_retries_and_accepts_no_content(self, delete, _sleep) -> None:
        delete.side_effect = [FakeResponse(503), FakeResponse(204)]

        deleted = PublicTOSStorage().delete("https://example.com/asr-temp/file.mp3")

        self.assertTrue(deleted)
        self.assertEqual(delete.call_count, 2)


if __name__ == "__main__":
    unittest.main()
