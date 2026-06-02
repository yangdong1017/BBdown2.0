from __future__ import annotations

from pathlib import Path

from qfluentwidgets import FluentIcon as FIF, FluentWindow, MessageBox

from core.config import WINDOW_TITLE
from core.media import is_media
from .asr_page import ASRPage
from .download_page import DownloadPage


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1220, 860)
        self.setMinimumSize(1060, 760)
        self.download_page = DownloadPage(self)
        self.asr_page = ASRPage(self)
        self.asr_page.request_download_dir.connect(self._use_download_dir)
        self.addSubInterface(self.download_page, FIF.DOWNLOAD, "批量下载")
        self.addSubInterface(self.asr_page, FIF.MICROPHONE, "批量转文字")
        self.navigationInterface.setExpandWidth(180)

    def _use_download_dir(self) -> None:
        directory = Path(self.download_page.config.save_dir)
        if not directory.is_dir():
            MessageBox("提示", "下载目录未设置或不存在。", self).exec()
            return
        files = [str(path) for path in sorted(directory.rglob("*")) if path.is_file() and is_media(path)]
        self.asr_page.add_files(files)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.download_page.is_running() or self.asr_page.is_running():
            box = MessageBox("确认退出", "任务正在运行中，确定要退出并停止它吗？", self)
            if not box.exec():
                event.ignore()
                return
            self.download_page._stop_all_tasks()
            self.asr_page.stop()
        event.accept()
