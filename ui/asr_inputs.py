from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import PushButton, TableWidget

from core.media import MEDIA_EXTENSIONS, is_media
from .widgets import TEXT_EDIT_STYLE


STATUS_COLORS = {
    "处理中": "#e5b84a",
    "已完成": "#7fd26f",
    "跳过": "#6aaee6",
    "失败": "#ff6a5c",
    "未处理": "#a8a8a8",
}


class LocalFileInput(QWidget):
    request_download_dir = pyqtSignal()
    files_added = pyqtSignal(int)
    cleared = pyqtSignal()

    def __init__(self, start_dir: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.start_dir = start_dir
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        actions = QHBoxLayout()
        self.add_files_btn = PushButton("选择音视频文件", self)
        self.add_files_btn.clicked.connect(self.select_files)
        self.add_folder_btn = PushButton("选择文件夹", self)
        self.add_folder_btn.clicked.connect(self.select_folder)
        self.use_download_dir_btn = PushButton("使用下载目录", self)
        self.use_download_dir_btn.clicked.connect(self.request_download_dir.emit)
        self.clear_btn = PushButton("清空列表", self)
        self.clear_btn.clicked.connect(self.clear)
        actions.addWidget(self.add_files_btn)
        actions.addWidget(self.add_folder_btn)
        actions.addWidget(self.use_download_dir_btn)
        actions.addWidget(self.clear_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.table = TableWidget(self)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "状态"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 90)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table, 1)

    def set_start_dir(self, directory: str) -> None:
        self.start_dir = directory

    def select_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音视频文件",
            self.start_dir,
            "音视频文件 (*.mp3 *.wav *.m4a *.flac *.aac *.ogg *.wma *.mp4 *.mkv *.flv *.mov *.avi *.wmv *.ts *.webm *.rmvb);;所有文件 (*)",
        )
        self.add_files(files)

    def select_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择文件夹", self.start_dir)
        if not directory:
            return
        files = [
            str(path)
            for path in Path(directory).rglob("*")
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        ]
        self.add_files(files)

    def add_files(self, files: list[str]) -> None:
        existing = {
            str(Path(self.table.item(row, 0).data(Qt.UserRole)).resolve())
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
        }
        added = 0
        for raw_path in files:
            path = Path(raw_path)
            if not path.is_file() or not is_media(path):
                continue
            resolved = str(path.resolve())
            if resolved in existing:
                continue
            self._append_file(path, resolved)
            existing.add(resolved)
            added += 1
        if added:
            self.files_added.emit(added)

    def clear(self) -> None:
        self.table.setRowCount(0)
        self.cleared.emit()

    def pending_files(self) -> list[tuple[int, str]]:
        files: list[tuple[int, str]] = []
        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, 2)
            name_item = self.table.item(row, 0)
            if not status_item or not name_item:
                continue
            if status_item.text() in ("未处理", "失败"):
                files.append((row, name_item.data(Qt.UserRole)))
        return files

    def set_file_status(self, row: int, status: str) -> None:
        if not 0 <= row < self.table.rowCount():
            return
        item = QTableWidgetItem(status)
        item.setForeground(QColor(STATUS_COLORS.get(status, "#cccccc")))
        self.table.setItem(row, 2, item)

    def first_source_directory(self) -> str:
        if self.table.rowCount() <= 0:
            return ""
        item = self.table.item(0, 0)
        path = item.data(Qt.UserRole) if item else ""
        return str(Path(path).parent) if path else ""

    def add_dropped_urls(self, urls) -> None:
        files: list[str] = []
        for url in urls:
            path = Path(url.toLocalFile())
            if path.is_dir():
                files.extend(str(item) for item in path.rglob("*") if item.is_file() and is_media(item))
            elif path.is_file() and is_media(path):
                files.append(str(path))
        self.add_files(files)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self.add_dropped_urls(event.mimeData().urls())

    def _append_file(self, path: Path, resolved: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        name_item = QTableWidgetItem(path.name)
        name_item.setData(Qt.UserRole, resolved)
        size_item = QTableWidgetItem(f"{path.stat().st_size / (1024 * 1024):.1f} MB")
        status_item = QTableWidgetItem("未处理")
        status_item.setForeground(QColor(STATUS_COLORS["未处理"]))
        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, size_item)
        self.table.setItem(row, 2, status_item)


class UrlInput(QWidget):
    cleared = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        actions = QHBoxLayout()
        self.clear_btn = PushButton("清空链接", self)
        self.clear_btn.clicked.connect(self.clear)
        actions.addWidget(self.clear_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.edit = QPlainTextEdit(self)
        self.edit.setPlaceholderText("粘贴抖音 mp3/wav 音频直链，一行一个；也可以粘贴包含音频直链的整段文本。")
        self.edit.setMinimumHeight(76)
        self.edit.setMaximumHeight(110)
        self.edit.setStyleSheet(TEXT_EDIT_STYLE)
        layout.addWidget(self.edit)

    def text(self) -> str:
        return self.edit.toPlainText()

    def set_failed_urls(self, urls: list[str]) -> None:
        self.edit.setPlainText("\n".join(urls))

    def clear(self) -> None:
        self.edit.clear()
        self.cleared.emit()
