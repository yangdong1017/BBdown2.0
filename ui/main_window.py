from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QTimer
from qfluentwidgets import FluentIcon as FIF, FluentWindow, MessageBox, NavigationItemPosition

from core.config import WINDOW_TITLE
from core.media import is_media
from .asr_page import ASRPage
from .brand_icons import brand_icon
from .download_page import DownloadPage
from .douyin_video_page import DouyinVideoPage
from .notice_page import NoticePage
from .settings_page import SettingsPage


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1220, 860)
        self.setMinimumSize(1060, 760)
        self._closing_after_stop = False
        self._allow_close = False
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(100)
        self._close_timer.timeout.connect(self._finish_close_when_idle)
        self.download_page = DownloadPage(self)
        self.douyin_video_page = DouyinVideoPage(self)
        self.asr_page = ASRPage(self)
        self.notice_page = NoticePage(self)
        self.settings_page = SettingsPage(self)
        self.asr_page.request_download_dir.connect(self._use_download_dir)
        self.addSubInterface(
            self.download_page,
            brand_icon("bilibili.ico", FIF.DOWNLOAD.icon()),
            "B站下载",
        )
        self.addSubInterface(
            self.douyin_video_page,
            brand_icon("douyin.ico", FIF.VIDEO.icon()),
            "抖音下载",
        )
        self.addSubInterface(self.asr_page, FIF.MICROPHONE, "批量转文字")
        self.addSubInterface(
            self.notice_page,
            FIF.INFO,
            "使用须知",
            position=NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(self.settings_page, FIF.SETTING, "设置", position=NavigationItemPosition.BOTTOM)
        self.navigationInterface.setExpandWidth(180)

    def _use_download_dir(self) -> None:
        directory = Path(self.download_page.config.save_dir)
        if not directory.is_dir():
            MessageBox("提示", "下载目录未设置或不存在。", self).exec()
            return
        files = [str(path) for path in sorted(directory.rglob("*")) if path.is_file() and is_media(path)]
        self.asr_page.add_files(files)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._allow_close:
            event.accept()
            return
        if self._closing_after_stop:
            event.ignore()
            return
        if self._has_running_tasks():
            box = MessageBox("确认退出", "任务正在运行中，确定要退出并停止它吗？", self)
            if not box.exec():
                event.ignore()
                return
            self._closing_after_stop = True
            self.setEnabled(False)
            self._stop_all_tasks()
            self._close_timer.start()
            event.ignore()
            return
        event.accept()

    def _has_running_tasks(self) -> bool:
        return any(
            (
                self.download_page.is_running(),
                self.douyin_video_page.is_running(),
                self.asr_page.is_running(),
            )
        )

    def _stop_all_tasks(self) -> None:
        self.download_page.stop()
        self.douyin_video_page.stop()
        self.asr_page.stop()

    def _finish_close_when_idle(self) -> None:
        if self._has_running_tasks():
            return
        self._close_timer.stop()
        self._allow_close = True
        self.close()
