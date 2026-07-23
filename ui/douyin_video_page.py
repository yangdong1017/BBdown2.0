from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    TableWidget,
    TextEdit,
    TitleLabel,
)

from core.config import (
    DOUYIN_VIDEO_CONCURRENCY_OPTIONS,
    LOG_DIR,
    WINDOW_TITLE,
    load_douyin_video_config,
    save_douyin_video_config,
)
from core.douyin_video_urls import DouyinVideoLink, extract_douyin_video_links
from core.douyin_video_worker import DouyinVideoWorkerThread
from core.models import DouyinVideoBatchResult
from .widgets import CardFrame, TEXT_EDIT_STYLE


STATUS_COLORS = {
    "等待中": "#a8a8a8",
    "下载中": "#e5b84a",
    "已完成": "#7fd26f",
    "已存在": "#6aaee6",
    "失败": "#ff6a5c",
    "已停止": "#a8a8a8",
}


class DouyinVideoPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("douyinVideoDownload")
        self.config = load_douyin_video_config()
        self.worker: DouyinVideoWorkerThread | None = None
        self.row_by_video_id: dict[str, int] = {}
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(350)
        self.save_timer.timeout.connect(self._save_config)
        self._build_ui()
        self._apply_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)
        root.addLayout(self._build_title_row())
        root.addWidget(self._build_input_card())
        root.addWidget(self._build_task_table(), 1)
        self.status_label = CaptionLabel("就绪", self)
        root.addWidget(self.status_label)

    def _build_title_row(self) -> QHBoxLayout:
        title_row = QHBoxLayout()
        title_row.addWidget(TitleLabel("抖音下载", self))
        title_row.addStretch(1)
        self.count_label = CaptionLabel("检测到 0 条可下载链接", self)
        title_row.addWidget(self.count_label)
        return title_row

    def _build_input_card(self) -> CardFrame:
        input_card = CardFrame(self)
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(18, 18, 18, 18)
        input_layout.setSpacing(10)
        input_layout.addWidget(BodyLabel("视频链接", input_card))
        self.url_edit = TextEdit(input_card)
        self.url_edit.setPlaceholderText(
            "粘贴 aweme.snssdk.com/aweme/v1/play/?video_id=... 视频链接，可一次粘贴整段文本。"
        )
        self.url_edit.setMinimumHeight(145)
        self.url_edit.setMaximumHeight(210)
        self.url_edit.setStyleSheet(TEXT_EDIT_STYLE)
        self.url_edit.textChanged.connect(self._on_text_changed)
        input_layout.addWidget(self.url_edit)
        input_layout.addLayout(self._build_settings_row(input_card))

        self.dir_label = CaptionLabel(input_card)
        self.dir_label.setWordWrap(True)
        input_layout.addWidget(self.dir_label)
        input_layout.addLayout(self._build_progress_row(input_card))
        input_layout.addLayout(self._build_action_row(input_card))
        return input_card

    def _build_settings_row(self, parent: QWidget) -> QHBoxLayout:
        settings_row = QHBoxLayout()
        self.choose_dir_btn = PushButton("更改保存目录", parent)
        self.choose_dir_btn.clicked.connect(self._choose_dir)
        self.open_dir_btn = PushButton("打开目录", parent)
        self.open_dir_btn.clicked.connect(self._open_save_dir)
        settings_row.addWidget(self.choose_dir_btn)
        settings_row.addWidget(self.open_dir_btn)
        settings_row.addStretch(1)
        settings_row.addWidget(BodyLabel("并发", parent))
        self.concurrency_combo = ComboBox(parent)
        self.concurrency_combo.addItems([str(value) for value in DOUYIN_VIDEO_CONCURRENCY_OPTIONS])
        self.concurrency_combo.currentTextChanged.connect(self._on_concurrency_changed)
        settings_row.addWidget(self.concurrency_combo)
        return settings_row

    def _build_progress_row(self, parent: QWidget) -> QHBoxLayout:
        progress_row = QHBoxLayout()
        self.progress_bar = ProgressBar(parent)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label = CaptionLabel("进度 0/0 | 进行中 0", parent)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_label)
        return progress_row

    def _build_action_row(self, parent: QWidget) -> QHBoxLayout:
        action_row = QHBoxLayout()
        self.start_btn = PrimaryPushButton("开始下载", parent)
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = PushButton("停止任务", parent)
        self.stop_btn.clicked.connect(self.stop)
        self.clear_btn = PushButton("清空链接", parent)
        self.clear_btn.clicked.connect(self._clear_links)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addWidget(self.clear_btn)
        action_row.addStretch(1)
        return action_row

    def _build_task_table(self) -> TableWidget:
        self.table = TableWidget(self)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["视频ID", "进度", "状态"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 180)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(False)
        return self.table

    def _apply_state(self) -> None:
        self.url_edit.setPlainText(self.config.urls)
        self.concurrency_combo.setCurrentText(str(self.config.concurrency))
        self._refresh_dir_label()
        self._set_running_state(False)
        self._refresh_link_count()

    def _on_text_changed(self) -> None:
        self._refresh_link_count()
        self.save_timer.start()

    def _refresh_link_count(self) -> None:
        count = len(extract_douyin_video_links(self.url_edit.toPlainText()))
        self.count_label.setText(f"检测到 {count} 条可下载链接")

    def _on_concurrency_changed(self, value: str) -> None:
        try:
            self.config.concurrency = int(value)
        except ValueError:
            return
        self.save_timer.start()

    def _save_config(self) -> None:
        self.config.urls = self.url_edit.toPlainText().strip()
        save_douyin_video_config(self.config)

    def _choose_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择保存目录",
            self.config.save_dir or str(Path.home() / "Downloads"),
        )
        if not directory:
            return
        self.config.save_dir = directory
        self._refresh_dir_label()
        self._save_config()

    def _refresh_dir_label(self) -> None:
        self.dir_label.setText(f"保存到：{self.config.save_dir}")

    def _open_save_dir(self) -> None:
        path = Path(self.config.save_dir)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            MessageBox("提示", "保存目录不可用，请重新选择。", self.window()).exec()
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _clear_links(self) -> None:
        if self.is_running():
            MessageBox("提示", "任务正在运行，请先停止任务。", self.window()).exec()
            return
        self.url_edit.clear()
        self.table.setRowCount(0)
        self.row_by_video_id.clear()
        self._on_batch_progress(0, 0, 0)
        self.status_label.setText("就绪")

    def _start_download(self) -> None:
        if self.is_running():
            return
        links = extract_douyin_video_links(self.url_edit.toPlainText())
        if not links:
            MessageBox("提示", "没有检测到可下载的视频链接。", self.window()).exec()
            return

        save_dir = Path(self.config.save_dir)
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            MessageBox("提示", "保存目录不可用，请重新选择。", self.window()).exec()
            return

        self._populate_tasks(links)
        self._save_config()
        self._write_log(f"开始下载，共 {len(links)} 个视频，并发 {self.config.concurrency}。")
        self._on_batch_progress(0, len(links), 0)

        self.worker = DouyinVideoWorkerThread(
            links=links,
            save_dir=str(save_dir),
            concurrency=self.config.concurrency,
            parent=self,
        )
        self.worker.log.connect(self._on_log)
        self.worker.status.connect(self.status_label.setText)
        self.worker.task_progress.connect(self._on_task_progress)
        self.worker.task_status.connect(self._on_task_status)
        self.worker.batch_progress.connect(self._on_batch_progress)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()
        self._set_running_state(True)

    def _populate_tasks(self, links: list[DouyinVideoLink]) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(links))
        self.row_by_video_id.clear()
        for row, link in enumerate(links):
            self.row_by_video_id[link.video_id] = row
            id_item = QTableWidgetItem(link.video_id)
            progress_item = QTableWidgetItem("0%")
            progress_item.setTextAlignment(Qt.AlignCenter)
            status_item = QTableWidgetItem("等待中")
            status_item.setForeground(QColor(STATUS_COLORS["等待中"]))
            self.table.setItem(row, 0, id_item)
            self.table.setItem(row, 1, progress_item)
            self.table.setItem(row, 2, status_item)
        self.table.setUpdatesEnabled(True)

    def _on_task_progress(self, video_id: str, downloaded: int, total: int) -> None:
        row = self.row_by_video_id.get(video_id)
        if row is None:
            return
        progress_item = self.table.item(row, 1)
        if progress_item is None:
            return
        if total > 0:
            progress_item.setText(f"{min(100, int(downloaded * 100 / total))}%")
        else:
            progress_item.setText(f"{downloaded / 1024 / 1024:.1f} MB")

    def _on_task_status(self, video_id: str, status: str, detail: str) -> None:
        row = self.row_by_video_id.get(video_id)
        if row is None:
            return
        status_item = self.table.item(row, 2)
        progress_item = self.table.item(row, 1)
        if status_item is not None:
            status_item.setText(f"{status}：{detail}" if detail and status == "失败" else status)
            status_item.setForeground(QColor(STATUS_COLORS.get(status, "#a8a8a8")))
        if progress_item is not None:
            if status in {"已完成", "已存在"}:
                progress_item.setText("100%")
            elif status in {"失败", "已停止"}:
                progress_item.setText("--")

    def _on_batch_progress(self, processed: int, total: int, active: int) -> None:
        percent = int(processed * 100 / total) if total else 0
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"进度 {processed}/{total} | {percent}% | 进行中 {active}")
        window = self.window()
        if window and total:
            window.setWindowTitle(f"BBDown - 抖音下载 {processed}/{total}")

    def _on_log(self, level: str, message: str) -> None:
        self._write_log(f"[{level.upper()}] {message}")

    def _write_log(self, message: str) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "douyin_video_download.log").open("a", encoding="utf-8") as output:
            output.write(message + "\n")

    def _on_finished(self, result: object) -> None:
        assert isinstance(result, DouyinVideoBatchResult)
        self.worker = None
        self._set_running_state(False)
        self.window().setWindowTitle(WINDOW_TITLE)
        if result.stopped:
            summary = (
                f"任务已停止：完成 {result.completed}，已存在 {result.skipped}，"
                f"失败 {result.failed}，停止 {result.stopped_count}。"
            )
        else:
            summary = f"下载结束：成功 {result.completed}，已存在 {result.skipped}，失败 {result.failed}。"
        self.status_label.setText(summary)
        self._write_log(summary)

    def _set_running_state(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.stop_btn.setText("停止任务")
        self.url_edit.setReadOnly(running)
        self.choose_dir_btn.setEnabled(not running)
        self.concurrency_combo.setEnabled(not running)
        self.clear_btn.setEnabled(not running)

    def stop(self) -> None:
        if not self.is_running() or self.worker is None:
            return
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("正在停止")
        self.worker.stop()

    def is_running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())
