from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core import config
from core.config import DOUBAO_ENGINE_NAME
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

    def test_url_input_builds_filename_size_status_task_table(self) -> None:
        panel = UrlInput()
        first_url = "https://example.com/music/first.mp3"
        second_url = "https://example.com/music/second.wav?token=1"

        panel.edit.setPlainText(f"{first_url}\n{second_url}")

        self.assertEqual(panel.table.rowCount(), 2)
        self.assertEqual(panel.table.horizontalHeaderItem(0).text(), "文件名")
        self.assertEqual(panel.table.horizontalHeaderItem(1).text(), "大小")
        self.assertEqual(panel.table.horizontalHeaderItem(2).text(), "状态")
        self.assertEqual(panel.table.item(0, 0).text(), "first.mp3")
        self.assertEqual(panel.table.item(1, 0).text(), "second.wav")
        self.assertEqual(panel.table.item(0, 1).text(), "待获取")
        self.assertEqual(panel.table.item(0, 2).text(), "等待中")
        self.assertEqual(panel.count_label.text(), "2 个有效链接")

        panel.set_task_metadata(0, "first.mp3", 2 * 1024 * 1024)
        panel.set_task_status(0, "识别中")
        self.assertEqual(panel.table.item(0, 1).text(), "2.0 MB")
        self.assertEqual(panel.table.item(0, 2).text(), "识别中")

        panel.set_failed_urls([second_url])
        self.assertEqual(panel.text(), second_url)
        self.assertEqual(panel.table.rowCount(), 2)
        self.assertEqual(panel.table.item(1, 2).text(), "失败")
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
                self.assertIn(DOUBAO_ENGINE_NAME, [page.engine_combo.itemText(i) for i in range(page.engine_combo.count())])
                page.engine_combo.setCurrentText(DOUBAO_ENGINE_NAME)
                self.assertEqual(page.format_combo.currentText(), "txt")
                self.assertFalse(page.format_combo.isEnabled())
                page.deleteLater()
        finally:
            config.CONFIG_PATH = original_path


if __name__ == "__main__":
    unittest.main()
