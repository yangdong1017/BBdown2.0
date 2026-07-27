from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from core import config
from core.bilibili_workers import DownloadWorkerThread
from core.commands import bilibili_display_id, build_download_command
from core.config import BILIBILI_AUDIO_DOWNLOAD, BILIBILI_VIDEO_DOWNLOAD
from core.models import AppConfig, Toolchain
from ui.download_page import BILIBILI_STANDARD_LINK, DownloadPage


class BilibiliDownloadCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.toolchain = Toolchain(
            bbdown=Path("BBDown.exe"),
            ffmpeg=Path("ffmpeg.exe"),
            aria2c=Path("aria2c.exe"),
        )

    def test_audio_mode_adds_audio_only(self) -> None:
        command = build_download_command(
            "https://www.bilibili.com/video/BV1test",
            "output",
            self.toolchain,
            download_type=BILIBILI_AUDIO_DOWNLOAD,
        )

        self.assertIn("--audio-only", command)
        self.assertNotIn("--video-only", command)

    def test_video_mode_downloads_picture_and_sound(self) -> None:
        command = build_download_command(
            "https://www.bilibili.com/video/BV1test",
            "output",
            self.toolchain,
            download_type=BILIBILI_VIDEO_DOWNLOAD,
        )

        self.assertNotIn("--audio-only", command)
        self.assertNotIn("--video-only", command)
        self.assertIn("--ffmpeg-path", command)
        self.assertEqual(command[command.index("--aria2c-args") + 1], "-x4 -s4 -j1 -k1M")

    def test_invalid_download_type_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "不支持的B站下载类型"):
            build_download_command(
                "https://www.bilibili.com/video/BV1test",
                "output",
                self.toolchain,
                download_type="unknown",
            )

    def test_bilibili_id_is_extracted_for_task_table(self) -> None:
        self.assertEqual(
            bilibili_display_id("https://www.bilibili.com/video/BV1v46zBzEX2/"),
            "BV1v46zBzEX2",
        )
        self.assertEqual(bilibili_display_id("https://www.bilibili.com/video/av12345"), "av12345")

    def test_worker_extracts_aria2_percentage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker = DownloadWorkerThread([], directory, 5, Toolchain(), Path(directory), "utf-8")
            progress: list[tuple[int, int]] = []
            worker.task_progress.connect(lambda index, percent: progress.append((index, percent)))

            worker._emit_task_progress_from_output(2, "[#1 SIZE/20MiB(67%) CN:4]")

            self.assertEqual(progress, [(2, 67)])


class BilibiliDownloadConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_path = config.CONFIG_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        config.CONFIG_PATH = Path(self.temp_dir.name) / "config.json"

    def tearDown(self) -> None:
        config.CONFIG_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_default_mode_is_audio(self) -> None:
        self.assertEqual(config.load_app_config().bilibili_download_type, BILIBILI_AUDIO_DOWNLOAD)

    def test_video_mode_is_persisted(self) -> None:
        config.update_app_config(bilibili_download_type=BILIBILI_VIDEO_DOWNLOAD)
        self.assertEqual(config.load_app_config().bilibili_download_type, BILIBILI_VIDEO_DOWNLOAD)

    def test_invalid_mode_falls_back_to_audio(self) -> None:
        config.update_app_config(bilibili_download_type="unknown")
        self.assertEqual(config.load_app_config().bilibili_download_type, BILIBILI_AUDIO_DOWNLOAD)


class BilibiliDownloadPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_download_type_selector_updates_ui_and_is_locked_while_running(self) -> None:
        page_config = AppConfig(save_dir=tempfile.gettempdir())
        with (
            patch("ui.download_page.load_app_config", return_value=page_config),
            patch("ui.download_page.resolve_toolchain", return_value=Toolchain()),
            patch("ui.download_page.update_app_config") as save_config,
        ):
            page = DownloadPage()
            self.assertEqual(page.download_type_segment.currentRouteKey(), BILIBILI_AUDIO_DOWNLOAD)
            self.assertEqual(page.start_btn.text(), "开始下载音频")
            self.assertEqual(page.url_edit.placeholderText(), "")

            save_config.reset_mock()
            page.download_type_segment.setCurrentItem(BILIBILI_VIDEO_DOWNLOAD)
            page._on_download_type_changed(BILIBILI_VIDEO_DOWNLOAD)

            self.assertEqual(page.config.bilibili_download_type, BILIBILI_VIDEO_DOWNLOAD)
            self.assertEqual(page.start_btn.text(), "开始下载视频")
            self.assertEqual(
                save_config.call_args.kwargs["bilibili_download_type"],
                BILIBILI_VIDEO_DOWNLOAD,
            )

            page._set_running_state(True)
            self.assertFalse(page.download_type_segment.isEnabled())
            page._set_running_state(False)
            self.assertTrue(page.download_type_segment.isEnabled())
            self.assertFalse(hasattr(page, "console"))
            self.assertFalse(hasattr(page, "log_btn"))
            page.deleteLater()

    def test_task_table_shows_video_id_progress_and_status(self) -> None:
        page_config = AppConfig(save_dir=tempfile.gettempdir())
        with (
            patch("ui.download_page.load_app_config", return_value=page_config),
            patch("ui.download_page.resolve_toolchain", return_value=Toolchain()),
            patch("ui.download_page.update_app_config"),
        ):
            page = DownloadPage()
            page._populate_tasks([BILIBILI_STANDARD_LINK])

            self.assertEqual(page.table.horizontalHeaderItem(0).text(), "视频ID")
            self.assertEqual(page.table.horizontalHeaderItem(1).text(), "进度")
            self.assertEqual(page.table.horizontalHeaderItem(2).text(), "状态")
            self.assertEqual(page.table.item(0, 0).text(), "BV1v46zBzEX2")
            self.assertEqual(page.table.item(0, 1).text(), "0%")
            self.assertEqual(page.table.item(0, 2).text(), "等待中")

            page._on_task_progress(1, 62)
            page._on_task_status(1, "下载中", "")
            self.assertEqual(page.table.item(0, 1).text(), "62%")
            self.assertEqual(page.table.item(0, 2).text(), "下载中")

            page._on_task_status(1, "已完成", "")
            self.assertEqual(page.table.item(0, 1).text(), "100%")
            self.assertEqual(page.table.item(0, 2).text(), "已完成")
            page.deleteLater()

    def test_standard_link_is_displayed_and_opened_in_browser(self) -> None:
        page_config = AppConfig(save_dir=tempfile.gettempdir())
        with (
            patch("ui.download_page.load_app_config", return_value=page_config),
            patch("ui.download_page.resolve_toolchain", return_value=Toolchain()),
            patch("ui.download_page.update_app_config"),
            patch("ui.download_page.QDesktopServices.openUrl", return_value=True) as open_url,
        ):
            page = DownloadPage()

            self.assertIn(BILIBILI_STANDARD_LINK, page.example_link_label.text())
            self.assertEqual(set(page.example_link_actions.items), {"copy", "open"})
            self.assertTrue(page.download_card.isAncestorOf(page.example_link_label))
            self.assertTrue(page.download_card.isAncestorOf(page.example_link_actions))
            self.assertTrue(page.right_panel.content.isAncestorOf(page.login_state_label))
            self.assertTrue(page.login_panel.isAncestorOf(page.login_state_label))
            self.assertFalse(page.download_card.isAncestorOf(page.login_state_label))
            self.assertEqual(page.download_card.layout().contentsMargins().top(), 9)
            self.assertEqual(page.download_card.layout().spacing(), 5)
            with patch("ui.download_page.QApplication.clipboard") as clipboard:
                page.example_link_actions.items["copy"].click()
                clipboard.return_value.setText.assert_called_once_with(BILIBILI_STANDARD_LINK)
            self.assertEqual(page.example_link_actions.currentRouteKey(), "copy")
            self.assertIn("已复制", page.status_label.text())
            page.example_link_actions.items["open"].click()
            self.assertEqual(page.example_link_actions.currentRouteKey(), "open")
            self.assertEqual(open_url.call_args.args[0].toString(), BILIBILI_STANDARD_LINK)
            page.deleteLater()

    def test_right_settings_panel_can_collapse_and_expand(self) -> None:
        page_config = AppConfig(save_dir=tempfile.gettempdir())
        with (
            patch("ui.download_page.load_app_config", return_value=page_config),
            patch("ui.download_page.resolve_toolchain", return_value=Toolchain()),
            patch("ui.download_page.update_app_config"),
        ):
            page = DownloadPage()
            page.resize(1020, 820)
            page.show()
            self.app.processEvents()

            self.assertTrue(page.right_panel.is_expanded)
            self.assertFalse(page.right_panel.content.isHidden())

            page.right_panel.toggle_button.click()
            QTest.qWait(260)
            self.assertFalse(page.right_panel.is_expanded)
            self.assertTrue(page.right_panel.content.isHidden())

            page.right_panel.toggle_button.click()
            QTest.qWait(260)
            self.assertTrue(page.right_panel.is_expanded)
            self.assertFalse(page.right_panel.content.isHidden())
            self.assertGreater(page.right_panel.content.width(), 0)
            page.close()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main()
