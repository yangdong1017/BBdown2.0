from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.asr_task import ASRTaskResult
from core.url_asr_worker import UrlASRWorkerThread
from core.url_audio import audio_filename_from_url, probe_audio_size


class UrlASRTaskTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_display_filename_keeps_audio_suffix(self) -> None:
        self.assertEqual(
            audio_filename_from_url("https://example.com/path/my%20audio.mp3?token=1", 0),
            "my_audio.mp3",
        )
        self.assertEqual(audio_filename_from_url("https://example.com/audio", 2), "audio")

    @patch("core.url_audio.requests.head")
    def test_remote_size_uses_content_length(self, head) -> None:
        head.return_value.headers = {"content-length": str(3 * 1024 * 1024)}
        head.return_value.raise_for_status.return_value = None

        self.assertEqual(probe_audio_size("https://example.com/audio.mp3"), 3 * 1024 * 1024)

    def test_worker_emits_metadata_and_status_before_result(self) -> None:
        url = "https://example.com/audio.mp3"
        with tempfile.TemporaryDirectory() as directory:
            worker = UrlASRWorkerThread([url], "必剪", "txt", 5, directory)
            metadata: list[tuple[int, str, int]] = []
            statuses: list[tuple[int, str]] = []
            worker.task_metadata.connect(lambda *args: metadata.append(args))
            worker.task_status.connect(lambda *args: statuses.append(args))

            with (
                patch("core.url_asr_worker.probe_audio_size", return_value=4 * 1024 * 1024),
                patch(
                    "core.url_asr_worker.process_url_asr_task",
                    return_value=ASRTaskResult(0, url, "ok", "audio.txt"),
                ),
            ):
                result = worker._process_one(0, url)

            self.assertEqual(result.status, "ok")
            self.assertEqual(metadata, [(0, "audio.mp3", 4 * 1024 * 1024)])
            self.assertEqual(statuses, [(0, "获取信息"), (0, "识别中")])


if __name__ == "__main__":
    unittest.main()
