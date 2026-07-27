from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core import config
from core.config_store import read_json
from core.models import DouyinVideoConfig


class DouyinVideoConfigTests(unittest.TestCase):
    def test_separate_settings_survive_other_config_saves(self) -> None:
        original_path = config.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                config.CONFIG_PATH = Path(directory) / "config.json"
                config.save_douyin_video_config(
                    DouyinVideoConfig(
                        urls="video-links",
                        save_dir="D:/videos",
                        concurrency=10,
                        audio_urls="audio-links",
                        download_type="audio",
                    )
                )
                config.update_app_config(last_urls="bilibili-links")

                payload = read_json(config.CONFIG_PATH)
                self.assertEqual(payload["douyin_video_urls"], "video-links")
                self.assertEqual(payload["douyin_audio_urls"], "audio-links")
                self.assertEqual(payload["douyin_download_type"], "audio")
                self.assertEqual(payload["douyin_video_save_dir"], "D:/videos")
                self.assertEqual(payload["douyin_video_concurrency"], 10)
                self.assertEqual(payload["last_urls"], "bilibili-links")

                loaded = config.load_douyin_video_config()
                self.assertEqual(loaded.audio_urls, "audio-links")
                self.assertEqual(loaded.download_type, "audio")
        finally:
            config.CONFIG_PATH = original_path

if __name__ == "__main__":
    unittest.main()
