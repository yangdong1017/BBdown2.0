from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core import config
from ui.asr_inputs import LocalFileInput, UrlInput
from ui.asr_page import ASRPage, DOUYIN_ASR_MODE


class ASRInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_local_input_filters_deduplicates_and_tracks_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "speech.mp3"
            ignored = root / "notes.txt"
            audio.write_bytes(b"audio")
            ignored.write_text("text", encoding="utf-8")
            added_counts: list[int] = []
            cleared: list[bool] = []
            panel = LocalFileInput(str(root))
            panel.files_added.connect(added_counts.append)
            panel.cleared.connect(lambda: cleared.append(True))

            panel.add_files([str(audio), str(audio), str(ignored)])

            self.assertEqual(panel.table.rowCount(), 1)
            self.assertEqual(added_counts, [1])
            self.assertEqual(panel.pending_files(), [(0, str(audio.resolve()))])
            self.assertEqual(panel.first_source_directory(), str(root))

            panel.set_file_status(0, "已完成")
            self.assertEqual(panel.pending_files(), [])
            panel.set_file_status(0, "失败")
            self.assertEqual(panel.pending_files(), [(0, str(audio.resolve()))])

            panel.clear()
            self.assertEqual(panel.table.rowCount(), 0)
            self.assertEqual(cleared, [True])
            panel.deleteLater()

    def test_url_input_refills_failed_urls(self) -> None:
        panel = UrlInput()
        cleared: list[bool] = []
        panel.cleared.connect(lambda: cleared.append(True))

        panel.set_failed_urls(["https://example.com/1.mp3", "https://example.com/2.mp3"])
        self.assertEqual(
            panel.text(),
            "https://example.com/1.mp3\nhttps://example.com/2.mp3",
        )
        panel.clear()
        self.assertEqual(panel.text(), "")
        self.assertEqual(cleared, [True])
        panel.deleteLater()

    def test_asr_page_switches_between_input_components(self) -> None:
        original_path = config.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                config.CONFIG_PATH = Path(directory) / "config.json"
                page = ASRPage()

                page.mode_combo.setCurrentText(DOUYIN_ASR_MODE)
                self.assertTrue(page.local_input.isHidden())
                self.assertFalse(page.url_input.isHidden())

                page.mode_combo.setCurrentText("音视频转文字")
                self.assertFalse(page.local_input.isHidden())
                self.assertTrue(page.url_input.isHidden())
                page.deleteLater()
        finally:
            config.CONFIG_PATH = original_path


if __name__ == "__main__":
    unittest.main()
