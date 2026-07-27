from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.asr_file_worker import ASRWorkerThread
from core.bilibili_workers import DownloadWorkerThread, LoginWorkerThread
from core.douyin_video_urls import DouyinVideoLink
from core.douyin_video_worker import DouyinMediaWorkerThread
from core.models import Toolchain
from core.url_asr_worker import UrlASRWorkerThread


class WorkerCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_asr_workers_emit_completion_after_batch_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file_worker = ASRWorkerThread([], "必剪", "txt", 5, directory, None)
            url_worker = UrlASRWorkerThread([], "必剪", "txt", 5, directory)
            file_results: list[str] = []
            url_results: list[object] = []
            file_worker.finished_all.connect(file_results.append)
            url_worker.finished_all.connect(url_results.append)

            with patch.object(file_worker, "_run_batch", side_effect=RuntimeError("broken")):
                file_worker.run()
            with patch.object(url_worker, "_run_batch", side_effect=RuntimeError("broken")):
                url_worker.run()

            self.assertEqual(len(file_results), 1)
            self.assertIn("任务异常", file_results[0])
            self.assertEqual(len(url_results), 1)
            self.assertIn("任务异常", url_results[0].summary)

    def test_download_workers_emit_completion_after_batch_exception(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bilibili = DownloadWorkerThread(
                ["https://example.com/video"],
                directory,
                5,
                Toolchain(),
                root,
                "utf-8",
            )
            douyin = DouyinMediaWorkerThread(
                [DouyinVideoLink("video-id", "https://example.com/video.mp4")],
                directory,
                5,
            )
            bilibili_results: list[object] = []
            douyin_results: list[object] = []
            bilibili.finished_all.connect(bilibili_results.append)
            douyin.finished_all.connect(douyin_results.append)

            with patch.object(bilibili, "_run_batch", side_effect=RuntimeError("broken")):
                bilibili.run()
            with patch.object(douyin, "_run_batch", side_effect=RuntimeError("broken")):
                douyin.run()

            self.assertEqual(len(bilibili_results), 1)
            self.assertEqual(bilibili_results[0].failed_urls, ["https://example.com/video"])
            self.assertEqual(len(douyin_results), 1)
            self.assertEqual(douyin_results[0].failed, 1)

    @patch("core.bilibili_workers.build_login_command", side_effect=RuntimeError("broken"))
    def test_login_worker_emits_completion_after_command_error(self, _build_command) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker = LoginWorkerThread("WEB 登录", Toolchain(), Path(directory), "utf-8")
            results: list[object] = []
            worker.finished_one.connect(results.append)

            worker.run()

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].return_code, 1)


if __name__ == "__main__":
    unittest.main()
