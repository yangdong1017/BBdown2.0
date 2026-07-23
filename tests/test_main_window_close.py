from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.main_window import MainWindow


class _FakePage:
    def __init__(self) -> None:
        self.running = True
        self.stop_called = False

    def is_running(self) -> bool:
        return self.running

    def stop(self) -> None:
        self.stop_called = True


class _FakeCloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class MainWindowCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_close_waits_until_all_pages_finish(self) -> None:
        window = MainWindow()
        pages = [_FakePage(), _FakePage(), _FakePage()]
        window.download_page, window.douyin_video_page, window.asr_page = pages
        event = _FakeCloseEvent()

        with patch("ui.main_window.MessageBox") as message_box:
            message_box.return_value.exec.return_value = True
            window.closeEvent(event)

        self.assertTrue(event.ignored)
        self.assertTrue(window._close_timer.isActive())
        self.assertTrue(all(page.stop_called for page in pages))

        for page in pages:
            page.running = False
        window._finish_close_when_idle()

        self.assertFalse(window._close_timer.isActive())
        self.assertTrue(window._allow_close)
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
