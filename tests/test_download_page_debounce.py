from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.models import AppConfig
from core.toolchain import Toolchain
from ui.download_page import DownloadPage


class DownloadPageSaveDebounceTests(unittest.TestCase):
    """Typing must not rewrite the whole config file on every keystroke."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _page(self) -> DownloadPage:
        """Build the page with a temporary config; update_app_config is already patched."""
        patches = [
            patch("ui.download_page.load_app_config", return_value=AppConfig(save_dir=tempfile.gettempdir())),
            patch("ui.download_page.resolve_toolchain", return_value=Toolchain()),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        page = DownloadPage()
        self.addCleanup(page.deleteLater)
        return page

    def test_typing_updates_count_without_writing_config(self) -> None:
        with patch("ui.download_page.update_app_config") as save_config:
            page = self._page()
            save_config.reset_mock()

            for count in range(1, 4):
                page.url_edit.setPlainText(
                    "\n".join(f"https://www.bilibili.com/video/BV1v46zBzEX{index}" for index in range(count))
                )

            self.assertEqual(save_config.call_count, 0)
            self.assertTrue(page.save_timer.isActive())
            self.assertEqual(page.count_label.text(), "3 个有效链接")

    def test_pending_edit_is_written_once_when_typing_stops(self) -> None:
        with patch("ui.download_page.update_app_config") as save_config:
            page = self._page()
            save_config.reset_mock()

            page.url_edit.setPlainText("https://www.bilibili.com/video/BV1v46zBzEX2/")
            page._save_config()

            self.assertEqual(save_config.call_count, 1)
            self.assertFalse(page.save_timer.isActive())
            self.assertEqual(
                save_config.call_args.kwargs["last_urls"],
                "https://www.bilibili.com/video/BV1v46zBzEX2/",
            )

    def test_flush_pending_save_writes_before_closing(self) -> None:
        with patch("ui.download_page.update_app_config") as save_config:
            page = self._page()
            save_config.reset_mock()

            page.url_edit.setPlainText("https://www.bilibili.com/video/BV1v46zBzEX2/")
            page.flush_pending_save()

            self.assertEqual(save_config.call_count, 1)
            # Nothing pending any more, so a second flush must stay silent.
            page.flush_pending_save()
            self.assertEqual(save_config.call_count, 1)

    def test_restoring_saved_links_does_not_write_config(self) -> None:
        with patch("ui.download_page.update_app_config") as save_config:
            self._page()
            self.assertEqual(save_config.call_count, 0)

    def test_parsed_links_are_reused_for_the_same_text(self) -> None:
        with patch("ui.download_page.update_app_config"):
            page = self._page()
            page.url_edit.setPlainText("https://www.bilibili.com/video/BV1v46zBzEX2/")

            first = page._parse_urls()
            second = page._parse_urls()

            self.assertEqual(first, ["https://www.bilibili.com/video/BV1v46zBzEX2/"])
            self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
