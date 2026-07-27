from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget

from core.atomic_io import write_text_atomic
from core.config import WINDOW_TITLE
from core.links import dedupe, is_douyin_cdn_host, iter_urls
from ui.platform_utils import open_directory
from ui.window_title import set_task_title


class LinkHelperTests(unittest.TestCase):
    def test_urls_are_found_in_free_text_without_trailing_punctuation(self) -> None:
        text = "看这个 https://a.example.com/x.mp3， 还有 (https://b.example.com/y.mp3) 这个。"

        self.assertEqual(
            list(iter_urls(text)),
            ["https://a.example.com/x.mp3", "https://b.example.com/y.mp3"],
        )

    def test_text_glued_straight_onto_a_url_is_a_known_limitation(self) -> None:
        # Known gap, unchanged from before: punctuation is only trimmed from the
        # very end, so "url，后面还有字" keeps the tail. Users paste one link per
        # line, or with a space after it, so this has not bitten anyone yet.
        self.assertEqual(
            list(iter_urls("https://a.example.com/x.mp3，还有")),
            ["https://a.example.com/x.mp3，还有"],
        )

    def test_empty_text_yields_nothing(self) -> None:
        self.assertEqual(list(iter_urls("")), [])

    def test_dedupe_keeps_first_occurrence_and_ignores_case(self) -> None:
        links = ["https://A.com/1", "https://a.com/1", " https://a.com/2 ", ""]

        self.assertEqual(dedupe(links), ["https://A.com/1", " https://a.com/2 "])

    def test_dedupe_can_use_a_key(self) -> None:
        items = [("a", 1), ("A", 2), ("b", 3)]

        self.assertEqual(dedupe(items, key=lambda item: item[0]), [("a", 1), ("b", 3)])

    def test_douyin_cdn_host_matches_subdomains_but_not_lookalikes(self) -> None:
        self.assertTrue(is_douyin_cdn_host("lf26-music-east.douyinstatic.com"))
        self.assertTrue(is_douyin_cdn_host("douyinvod.com"))
        # A domain that merely contains the name must not pass.
        self.assertFalse(is_douyin_cdn_host("douyinstatic.com.attacker.net"))
        self.assertFalse(is_douyin_cdn_host("notdouyinstatic.com"))
        self.assertFalse(is_douyin_cdn_host(""))


class AtomicWriteTests(unittest.TestCase):
    def test_text_is_written_and_no_temp_file_is_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sub" / "out.txt"

            write_text_atomic(target, "转写结果")

            self.assertEqual(target.read_text(encoding="utf-8"), "转写结果")
            self.assertEqual([item.name for item in target.parent.iterdir()], ["out.txt"])

    def test_stopping_before_the_write_leaves_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.txt"

            with self.assertRaises(RuntimeError):
                write_text_atomic(target, "结果", lambda: True)

            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_stopping_after_the_write_does_not_replace_the_old_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "out.txt"
            target.write_text("旧结果", encoding="utf-8")
            calls = {"count": 0}

            def stopped() -> bool:
                calls["count"] += 1
                return calls["count"] > 1

            with self.assertRaises(RuntimeError):
                write_text_atomic(target, "新结果", stopped)

            self.assertEqual(target.read_text(encoding="utf-8"), "旧结果")
            self.assertEqual([item.name for item in Path(directory).iterdir()], ["out.txt"])


class OpenDirectoryTests(unittest.TestCase):
    def test_missing_directory_reports_failure(self) -> None:
        self.assertFalse(open_directory("/definitely/not/here"))

    def test_a_file_is_not_a_directory(self) -> None:
        with tempfile.NamedTemporaryFile() as handle:
            self.assertFalse(open_directory(handle.name))

    def test_existing_directory_is_handed_to_the_file_manager(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("ui.platform_utils.subprocess.Popen") as popen:
                with patch("ui.platform_utils.sys.platform", "linux"):
                    self.assertTrue(open_directory(directory))
            popen.assert_called_once_with(["xdg-open", directory])

    def test_a_refusing_system_reports_failure_instead_of_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch("ui.platform_utils.sys.platform", "linux"):
                with patch("ui.platform_utils.subprocess.Popen", side_effect=OSError):
                    self.assertFalse(open_directory(directory))


class WindowTitleTests(unittest.TestCase):
    """The title bar must not stay stuck on a job that already ended."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_progress_is_shown_and_then_restored(self) -> None:
        window = QWidget()
        window.setWindowTitle(WINDOW_TITLE)
        page = QWidget(window)
        self.addCleanup(window.deleteLater)

        set_task_title(page, "B站下载 3/12")
        self.assertEqual(window.windowTitle(), "BBDown - B站下载 3/12")

        set_task_title(page)
        self.assertEqual(window.windowTitle(), WINDOW_TITLE)


if __name__ == "__main__":
    unittest.main()
