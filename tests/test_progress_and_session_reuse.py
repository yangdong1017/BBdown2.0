from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.bilibili_workers import DownloadWorkerThread
from core.douyin_video_downloader import DouyinMediaDownloader
from core.douyin_video_urls import DouyinVideoLink
from core.douyin_video_worker import DouyinMediaWorkerThread
from core.toolchain import Toolchain


VIDEO_DATA = b"\x00\x00\x00\x18ftypmp42" + (b"video-data" * 512)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(VIDEO_DATA)))
        self.end_headers()
        self.wfile.write(VIDEO_DATA)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class ConnectionPoolReuseTests(unittest.TestCase):
    """A batch must share one connection pool instead of reconnecting per task."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_repeated_downloads_reuse_one_session(self) -> None:
        downloader = DouyinMediaDownloader(threading.Event(), lambda *_args: None)
        with tempfile.TemporaryDirectory() as directory:
            sessions = []
            for index in range(3):
                link = DouyinVideoLink(video_id=f"clip{index}", url=f"{self.base_url}/media.mp4")
                result = downloader.download(link, Path(directory))
                self.assertEqual(result.status, "completed")
                sessions.append(downloader._session)

            self.assertIsNotNone(sessions[0])
            self.assertTrue(all(session is sessions[0] for session in sessions))

        downloader.close()
        self.assertIsNone(downloader._session)

    def test_pool_size_follows_concurrency(self) -> None:
        downloader = DouyinMediaDownloader(threading.Event(), lambda *_args: None, pool_size=20)
        session = downloader._session_for_download()
        adapter = session.get_adapter("https://example.com")

        self.assertEqual(adapter._pool_maxsize, 20)
        downloader.close()

    def test_stop_closes_the_session(self) -> None:
        downloader = DouyinMediaDownloader(threading.Event(), lambda *_args: None)
        downloader._session_for_download()
        downloader.stop()

        self.assertIsNone(downloader._session)


class ProgressThrottlingTests(unittest.TestCase):
    def test_douyin_progress_updates_are_sent_in_batches(self) -> None:
        worker = DouyinMediaWorkerThread(links=[], save_dir=tempfile.gettempdir(), concurrency=5)
        batches: list[dict] = []
        worker.task_progress.connect(batches.append)
        worker._last_progress_flush = time.monotonic()

        # Rapid updates inside one interval must not each become a signal.
        worker._emit_task_progress("a", 10, 100)
        worker._emit_task_progress("b", 20, 100)
        worker._emit_task_progress("a", 30, 100)
        self.assertEqual(batches, [])

        worker._flush_task_progress()

        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0], {"a": (30, 100), "b": (20, 100)})

        # Nothing buffered: an extra flush must stay silent.
        worker._flush_task_progress()
        self.assertEqual(len(batches), 1)

    def test_douyin_first_update_after_the_interval_is_sent_immediately(self) -> None:
        worker = DouyinMediaWorkerThread(links=[], save_dir=tempfile.gettempdir(), concurrency=5)
        batches: list[dict] = []
        worker.task_progress.connect(batches.append)
        worker._last_progress_flush = 0.0

        worker._emit_task_progress("a", 10, 100)

        self.assertEqual(batches, [{"a": (10, 100)}])

    def test_bilibili_repeats_the_same_percent_only_once(self) -> None:
        worker = DownloadWorkerThread(
            urls=[],
            save_dir=tempfile.gettempdir(),
            thread_count=5,
            toolchain=Toolchain(),
            runtime_dir=Path(tempfile.gettempdir()),
            output_encoding="utf-8",
        )
        updates: list[tuple[int, int]] = []
        worker.task_progress.connect(lambda index, percent: updates.append((index, percent)))

        worker._emit_task_progress_from_output(1, "[#1 SIZE/20MiB(67%) CN:4]")
        worker._emit_task_progress_from_output(1, "[#1 SIZE/20MiB(67%) CN:4]")
        worker._emit_task_progress_from_output(1, "[#1 SIZE/20MiB(68%) CN:4]")
        worker._emit_task_progress_from_output(2, "[#1 SIZE/20MiB(67%) CN:4]")

        self.assertEqual(updates, [(1, 67), (1, 68), (2, 67)])


if __name__ == "__main__":
    unittest.main()
