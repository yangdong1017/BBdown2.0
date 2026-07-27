from __future__ import annotations

import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.douyin_audio_urls import DouyinAudioLink
from core.douyin_video_downloader import DouyinMediaDownloader, DouyinVideoDownloader
from core.douyin_video_urls import DouyinVideoLink


VIDEO_DATA = b"\x00\x00\x00\x18ftypmp42" + (b"video-data" * 1024)
AUDIO_DATA = b"ID3" + (b"audio-data" * 1024)


class VideoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/play":
            self.send_response(302)
            self.send_header("Location", "/media.mp4")
            self.end_headers()
            return
        if self.path == "/media.mp4":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(VIDEO_DATA)))
            self.end_headers()
            self.wfile.write(VIDEO_DATA)
            return
        if self.path == "/media.mp3":
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(AUDIO_DATA)))
            self.end_headers()
            self.wfile.write(AUDIO_DATA)
            return
        if self.path == "/slow.mp4":
            chunk = b"x" * 65536
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(chunk) * 64))
            self.end_headers()
            try:
                for _ in range(64):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    time.sleep(0.03)
            except OSError:
                pass
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class DouyinVideoDownloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), VideoHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def test_downloads_video_through_redirect_and_skips_existing_file(self) -> None:
        progress: list[tuple[str, int, int]] = []
        downloader = DouyinVideoDownloader(threading.Event(), lambda *args: progress.append(args))
        link = DouyinVideoLink(video_id="test_video", url=f"{self.base_url}/play")

        with tempfile.TemporaryDirectory() as directory:
            result = downloader.download(link, Path(directory))
            target = Path(directory) / "test_video.mp4"

            self.assertEqual(result.status, "completed")
            self.assertEqual(target.read_bytes(), VIDEO_DATA)
            self.assertFalse((Path(directory) / "test_video.mp4.part").exists())
            self.assertTrue(progress)

            existing = downloader.download(link, Path(directory))
            self.assertEqual(existing.status, "exists")

    def test_reports_expired_link_without_partial_file(self) -> None:
        downloader = DouyinVideoDownloader(threading.Event(), lambda *_args: None)
        link = DouyinVideoLink(video_id="missing", url=f"{self.base_url}/missing")

        with tempfile.TemporaryDirectory() as directory:
            result = downloader.download(link, Path(directory))

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.message, "视频链接已失效")
            self.assertFalse((Path(directory) / "missing.mp4.part").exists())

    def test_downloads_audio_as_mp3_and_rejects_video_response(self) -> None:
        downloader = DouyinMediaDownloader(threading.Event(), lambda *_args: None)
        audio_link = DouyinAudioLink(
            audio_id="test_audio",
            url=f"{self.base_url}/media.mp3",
            suffix=".mp3",
        )
        wrong_link = DouyinAudioLink(
            audio_id="wrong_audio",
            url=f"{self.base_url}/media.mp4",
            suffix=".mp3",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = downloader.download(audio_link, root)
            wrong = downloader.download(wrong_link, root)

            self.assertEqual(result.status, "completed")
            self.assertEqual((root / "test_audio.mp3").read_bytes(), AUDIO_DATA)
            self.assertEqual(wrong.status, "failed")
            self.assertEqual(wrong.message, "该链接没有返回音频")
            self.assertFalse((root / "wrong_audio.mp3.part").exists())

    def test_honors_stop_before_starting(self) -> None:
        stop_event = threading.Event()
        stop_event.set()
        downloader = DouyinVideoDownloader(stop_event, lambda *_args: None)
        link = DouyinVideoLink(video_id="stopped", url=f"{self.base_url}/play")

        with tempfile.TemporaryDirectory() as directory:
            result = downloader.download(link, Path(directory))

            self.assertEqual(result.status, "stopped")
            self.assertFalse((Path(directory) / "stopped.mp4.part").exists())

    def test_stops_active_download_and_removes_partial_file(self) -> None:
        first_progress = threading.Event()
        stop_event = threading.Event()
        downloader = DouyinVideoDownloader(
            stop_event,
            lambda _video_id, downloaded, _total: first_progress.set() if downloaded else None,
        )
        link = DouyinVideoLink(video_id="active_stop", url=f"{self.base_url}/slow.mp4")
        result_holder = []

        with tempfile.TemporaryDirectory() as directory:
            thread = threading.Thread(
                target=lambda: result_holder.append(downloader.download(link, Path(directory)))
            )
            thread.start()
            self.assertTrue(first_progress.wait(timeout=2))
            downloader.stop()
            thread.join(timeout=3)

            self.assertFalse(thread.is_alive())
            self.assertEqual(result_holder[0].status, "stopped")
            self.assertFalse((Path(directory) / "active_stop.mp4.part").exists())


if __name__ == "__main__":
    unittest.main()
