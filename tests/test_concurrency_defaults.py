from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.asr_file_worker import ASRWorkerThread
from core.bilibili_workers import DownloadWorkerThread
from core.commands import build_aria2_args
from core.config import (
    ALL_ASR_CONCURRENCY_OPTIONS,
    DEFAULT_ASR_CONCURRENCY,
    DEFAULT_DOUYIN_VIDEO_CONCURRENCY,
    DEFAULT_THREAD_COUNT,
    DOUYIN_VIDEO_CONCURRENCY_OPTIONS,
    MIN_CONCURRENCY,
    THREAD_OPTIONS,
)
from core.douyin_video_worker import DouyinVideoWorkerThread
from core.models import Toolchain
from core.url_asr_worker import UrlASRWorkerThread


class ConcurrencyDefaultsTests(unittest.TestCase):
    def test_all_defaults_and_options_are_at_least_five(self) -> None:
        self.assertEqual(MIN_CONCURRENCY, 5)
        self.assertGreaterEqual(DEFAULT_THREAD_COUNT, MIN_CONCURRENCY)
        self.assertGreaterEqual(DEFAULT_ASR_CONCURRENCY, MIN_CONCURRENCY)
        self.assertGreaterEqual(DEFAULT_DOUYIN_VIDEO_CONCURRENCY, MIN_CONCURRENCY)
        self.assertTrue(all(value >= MIN_CONCURRENCY for value in THREAD_OPTIONS))
        self.assertTrue(all(value >= MIN_CONCURRENCY for value in ALL_ASR_CONCURRENCY_OPTIONS))
        self.assertTrue(all(value >= MIN_CONCURRENCY for value in DOUYIN_VIDEO_CONCURRENCY_OPTIONS))

    def test_workers_clamp_lower_values_and_aria2_uses_fixed_connections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bilibili = DownloadWorkerThread([], directory, 1, Toolchain(), root, "utf-8")
            douyin = DouyinVideoWorkerThread([], directory, 1)
            local_asr = ASRWorkerThread([], "必剪", "txt", 1, directory, None)
            url_asr = UrlASRWorkerThread([], "必剪", "txt", 1, directory)

            self.assertEqual(bilibili.thread_count, 5)
            self.assertEqual(douyin.concurrency, 5)
            self.assertEqual(local_asr.concurrency, 5)
            self.assertEqual(url_asr.concurrency, 5)
            self.assertEqual(build_aria2_args(), "-x4 -s4 -j1 -k1M")


if __name__ == "__main__":
    unittest.main()
