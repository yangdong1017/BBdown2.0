"""The three-column task table shared by the download pages."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem, QWidget
from qfluentwidgets import TableWidget


DEFAULT_STATUS_COLOR = "#a8a8a8"
STATUS_COLORS = {
    "等待中": DEFAULT_STATUS_COLOR,
    "下载中": "#e5b84a",
    "已完成": "#7fd26f",
    "已存在": "#6aaee6",
    "失败": "#ff6a5c",
    "已停止": DEFAULT_STATUS_COLOR,
}
FINISHED_STATUSES = ("已完成", "已存在")
GAVE_UP_STATUSES = ("失败", "已停止")

ID_COLUMN = 0
PROGRESS_COLUMN = 1
STATUS_COLUMN = 2


class TaskTable(TableWidget):
    """Shows one row per task: what it is, how far along, and how it ended.

    Rows are addressed by row number; each page keeps its own way of finding the
    row for a task, because B站 counts tasks and 抖音 names them.
    """

    def __init__(self, parent: QWidget | None = None, *, id_header: str = "视频ID") -> None:
        super().__init__(parent)
        self.setBorderVisible(True)
        self.setBorderRadius(8)
        self.setColumnCount(3)
        self.set_id_header(id_header)
        header = self.horizontalHeader()
        header.setSectionResizeMode(ID_COLUMN, QHeaderView.Stretch)
        header.setSectionResizeMode(PROGRESS_COLUMN, QHeaderView.Fixed)
        header.setSectionResizeMode(STATUS_COLUMN, QHeaderView.Fixed)
        self.setColumnWidth(PROGRESS_COLUMN, 110)
        self.setColumnWidth(STATUS_COLUMN, 180)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(False)

    def set_id_header(self, id_header: str) -> None:
        self.setHorizontalHeaderLabels([id_header, "进度", "状态"])

    def populate(self, names: list[str]) -> None:
        """Fill the table with one waiting row per task."""
        self.setUpdatesEnabled(False)
        try:
            self.setRowCount(len(names))
            for row, name in enumerate(names):
                progress_item = QTableWidgetItem("0%")
                progress_item.setTextAlignment(Qt.AlignCenter)
                status_item = QTableWidgetItem("等待中")
                status_item.setForeground(QColor(STATUS_COLORS["等待中"]))
                self.setItem(row, ID_COLUMN, QTableWidgetItem(name))
                self.setItem(row, PROGRESS_COLUMN, progress_item)
                self.setItem(row, STATUS_COLUMN, status_item)
        finally:
            self.setUpdatesEnabled(True)

    def set_percent(self, row: int, percent: int) -> None:
        item = self.item(row, PROGRESS_COLUMN)
        if item is not None:
            item.setText(f"{min(100, max(0, percent))}%")

    def set_progress_text(self, row: int, text: str) -> None:
        item = self.item(row, PROGRESS_COLUMN)
        if item is not None:
            item.setText(text)

    def set_status(self, row: int, status: str, detail: str = "") -> None:
        """Update the status cell, and settle the progress cell if the task ended."""
        status_item = self.item(row, STATUS_COLUMN)
        if status_item is not None:
            status_item.setText(f"{status}：{detail}" if status == "失败" and detail else status)
            status_item.setForeground(QColor(STATUS_COLORS.get(status, DEFAULT_STATUS_COLOR)))

        progress_item = self.item(row, PROGRESS_COLUMN)
        if progress_item is None:
            return
        if status in FINISHED_STATUSES:
            progress_item.setText("100%")
        elif status in GAVE_UP_STATUSES:
            progress_item.setText("--")
