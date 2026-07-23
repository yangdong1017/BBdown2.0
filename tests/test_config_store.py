from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import config
from core.config_store import atomic_write_json, read_json, update_json


class ConfigStoreTests(unittest.TestCase):
    def test_stale_page_state_does_not_overwrite_api_key(self) -> None:
        original_path = config.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                config.CONFIG_PATH = Path(directory) / "config.json"
                stale_page_config = config.load_app_config()
                config.save_doubao_api_key("new-api-key")

                config.update_app_config(
                    last_urls="bilibili-links",
                    save_dir=stale_page_config.save_dir,
                    thread_count=stale_page_config.thread_count,
                )

                self.assertEqual(config.load_doubao_api_key(), "new-api-key")
        finally:
            config.CONFIG_PATH = original_path

    def test_concurrent_partial_updates_keep_all_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            updates = [{f"field_{index}": index} for index in range(20)]
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda values: update_json(path, **values), updates))

            payload = read_json(path)
            self.assertEqual(payload, {f"field_{index}": index for index in range(20)})

    def test_failed_atomic_write_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            atomic_write_json(path, {"stable": True})

            with self.assertRaises(TypeError):
                atomic_write_json(path, {"invalid": object()})

            self.assertEqual(read_json(path), {"stable": True})
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_unknown_app_config_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知配置项"):
            config.update_app_config(unknown_setting=True)


if __name__ == "__main__":
    unittest.main()
