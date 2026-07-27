from __future__ import annotations

import locale
from pathlib import Path

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QTimer, QUrl, Qt
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    FluentIcon as FIF,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SegmentedWidget,
    TableWidget,
    TextEdit,
    TitleLabel,
    ToolButton,
)

from core.commands import bilibili_display_id, looks_like_video_input
from core.config import (
    ARIA2_CONNECTIONS_PER_TASK,
    BILIBILI_AUDIO_DOWNLOAD,
    BILIBILI_VIDEO_DOWNLOAD,
    RUNTIME_DIR,
    THREAD_OPTIONS,
    load_app_config,
    update_app_config,
)
from core.bilibili_workers import DownloadWorkerThread
from core.links import dedupe
from core.models import AppConfig, DownloadBatchResult
from core.toolchain import resolve_toolchain
from .bilibili_login_panel import BilibiliLoginPanel
from .platform_utils import open_directory
from .widgets import CardFrame, TEXT_EDIT_STYLE


BILIBILI_STANDARD_LINK = "https://www.bilibili.com/video/BV1v46zBzEX2/"
# Writing the config on every keystroke rewrites the whole JSON file. Wait until
# the user stops typing, the same way the Douyin page already does.
CONFIG_SAVE_DELAY_MS = 350
BILIBILI_STATUS_COLORS = {
    "等待中": "#a8a8a8",
    "下载中": "#e5b84a",
    "已完成": "#7fd26f",
    "失败": "#ff6a5c",
    "已停止": "#a8a8a8",
}


class DownloadPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("download")
        self.config: AppConfig = load_app_config()
        self.toolchain = resolve_toolchain()
        self.download_worker: DownloadWorkerThread | None = None
        self.failed_urls: list[str] = []
        self.no_output_urls: list[str] = []
        self._parsed_urls_cache: tuple[str, list[str]] | None = None
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(CONFIG_SAVE_DELAY_MS)
        self.save_timer.timeout.connect(self._save_config)
        self._build_ui()
        self._apply_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)
        root.addWidget(TitleLabel("B站下载", self))

        self.engine_label = CaptionLabel(self)
        self.engine_label.setVisible(False)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.download_type_segment = SegmentedWidget(self)
        self.download_type_segment.addItem(
            BILIBILI_AUDIO_DOWNLOAD,
            "下载音频",
            lambda: self._on_download_type_changed(BILIBILI_AUDIO_DOWNLOAD),
        )
        self.download_type_segment.addItem(
            BILIBILI_VIDEO_DOWNLOAD,
            "下载视频",
            lambda: self._on_download_type_changed(BILIBILI_VIDEO_DOWNLOAD),
        )
        self.download_type_segment.setFixedWidth(200)
        top_row.addWidget(self.download_type_segment)
        top_row.addStretch(1)
        root.addLayout(top_row)

        split = QHBoxLayout()
        split.setSpacing(6)
        root.addLayout(split, 1)

        self.left_panel = QWidget(self)
        left = QVBoxLayout(self.left_panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(14)
        self.download_card = self._build_download_card()
        left.addWidget(self.download_card, 6)
        left.addWidget(self._build_task_table(), 4)
        split.addWidget(self.left_panel, 1)

        self.right_panel_toggle = ToolButton(self)
        self.right_panel_toggle.setIcon(FIF.CARE_RIGHT_SOLID)
        self.right_panel_toggle.setFixedSize(26, 72)
        self.right_panel_toggle.setToolTip("收起右侧面板")
        self.right_panel_toggle.clicked.connect(self._toggle_right_panel)
        split.addWidget(self.right_panel_toggle, 0, Qt.AlignVCenter)

        self.right_panel = QWidget(self)
        self.right_panel.setMinimumWidth(0)
        self.right_panel.setMaximumWidth(400)
        right = QVBoxLayout(self.right_panel)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(14)
        right.addWidget(self._build_settings_card())
        right.addWidget(self._build_login_panel(), 1)
        split.addWidget(self.right_panel)

        self.right_panel_expanded = True
        self.right_panel_animation = QPropertyAnimation(self.right_panel, b"maximumWidth", self)
        self.right_panel_animation.setDuration(220)
        self.right_panel_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.right_panel_animation.finished.connect(self._on_right_panel_animation_finished)

        self.status_label = CaptionLabel("就绪", self)
        root.addWidget(self.status_label)

    def _build_download_card(self) -> CardFrame:
        content_card = CardFrame(self)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(18, 9, 18, 18)
        content_layout.setSpacing(5)

        standard_link_row = QHBoxLayout()
        standard_link_row.setSpacing(10)
        self.example_link_label = CaptionLabel(
            f"标准链接格式：{BILIBILI_STANDARD_LINK}",
            content_card,
        )
        self.example_link_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.example_link_label.setWordWrap(True)
        self.example_link_actions = SegmentedWidget(content_card)
        self.example_link_actions.addItem("copy", "复制", self._copy_example_link)
        self.example_link_actions.addItem("open", "打开", self._open_example_link)
        self.example_link_actions.setFixedWidth(150)
        standard_link_row.addWidget(self.example_link_label, 1)
        standard_link_row.addWidget(self.example_link_actions)
        content_layout.addLayout(standard_link_row)

        self.url_edit = TextEdit(content_card)
        self.url_edit.setMinimumHeight(260)
        self.url_edit.setStyleSheet(TEXT_EDIT_STYLE)
        self.url_edit.textChanged.connect(self._on_text_changed)
        content_layout.addWidget(self.url_edit)

        count_row = QHBoxLayout()
        self.count_label = CaptionLabel("0 个有效链接", content_card)
        self.clean_btn = PushButton("去重/清理", content_card)
        self.clean_btn.clicked.connect(self._clean_urls)
        count_row.addWidget(self.count_label)
        count_row.addStretch(1)
        count_row.addWidget(self.clean_btn)
        content_layout.addLayout(count_row)

        progress_row = QHBoxLayout()
        self.progress_bar = ProgressBar(content_card)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label = CaptionLabel("进度 0/0", content_card)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_label)
        content_layout.addLayout(progress_row)

        action_row = QHBoxLayout()
        self.start_btn = PrimaryPushButton("开始下载", content_card)
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = PushButton("停止任务", content_card)
        self.stop_btn.clicked.connect(self.stop)
        self.reset_btn = PushButton("清空任务", content_card)
        self.reset_btn.clicked.connect(self._reset_task)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch(1)
        content_layout.addLayout(action_row)
        return content_card

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

    def _build_settings_card(self) -> CardFrame:
        settings_card = CardFrame(self)
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(18, 18, 18, 18)
        settings_layout.setSpacing(12)
        settings_layout.addWidget(BodyLabel("下载设置", settings_card))

        dir_row = QHBoxLayout()
        self.choose_dir_btn = PushButton("选择保存目录", settings_card)
        self.choose_dir_btn.clicked.connect(self._choose_dir)
        self.open_dir_btn = PushButton("打开目录", settings_card)
        self.open_dir_btn.clicked.connect(self._open_save_dir)
        dir_row.addWidget(self.choose_dir_btn)
        dir_row.addWidget(self.open_dir_btn)
        settings_layout.addLayout(dir_row)

        self.dir_label = CaptionLabel(settings_card)
        self.dir_label.setWordWrap(True)
        settings_layout.addWidget(self.dir_label)

        thread_row = QHBoxLayout()
        thread_row.addWidget(BodyLabel("并发", settings_card))
        self.thread_combo = ComboBox(settings_card)
        for value in THREAD_OPTIONS:
            self.thread_combo.addItem(str(value))
        self.thread_combo.currentTextChanged.connect(self._on_thread_changed)
        thread_row.addWidget(self.thread_combo)
        thread_row.addStretch(1)
        settings_layout.addLayout(thread_row)

        return settings_card

    def _build_login_panel(self) -> BilibiliLoginPanel:
        self.login_panel = BilibiliLoginPanel(
            toolchain=self.toolchain,
            runtime_dir=RUNTIME_DIR,
            save_dir=self.config.save_dir,
            parent=self,
        )
        self.login_state_label = self.login_panel.login_state_label
        self.login_panel.status.connect(self._set_status)
        return self.login_panel

    def _apply_state(self) -> None:
        self.url_edit.blockSignals(True)
        self.url_edit.setPlainText(self.config.last_urls)
        self.url_edit.blockSignals(False)
        self.thread_combo.setCurrentText(str(self.config.thread_count))
        self.download_type_segment.setCurrentItem(self.config.bilibili_download_type)
        self._refresh_engine_status()
        self.login_panel.refresh_login_status()
        self._refresh_dir_label()
        self._refresh_download_type_ui()
        self._set_running_state(False)
        self._update_count()

    def _refresh_engine_status(self) -> None:
        state = "已连接" if self.toolchain.bbdown else "未找到"
        ffmpeg_name = self.toolchain.ffmpeg.name if self.toolchain.ffmpeg else "未检测到"
        aria2_desc = f"{ARIA2_CONNECTIONS_PER_TASK}连接/任务" if self.toolchain.aria2c else "未检测到"
        self.engine_label.setText(
            f"引擎: {self.toolchain.bbdown or '未找到'} | 状态: {state} | ffmpeg: {ffmpeg_name} | aria2c: {aria2_desc} | 批量并发: {self.config.thread_count}"
        )

    def _refresh_dir_label(self) -> None:
        display = self.config.save_dir
        if len(display) > 58:
            display = "..." + display[-55:]
        suffix = "" if Path(self.config.save_dir).exists() else " (目录不存在)"
        self.dir_label.setText(f"保存到: {display}{suffix}")

    def _refresh_download_type_ui(self) -> None:
        is_video = self.config.bilibili_download_type == BILIBILI_VIDEO_DOWNLOAD
        self.start_btn.setText("开始下载视频" if is_video else "开始下载音频")

    def _save_config(self) -> None:
        self.save_timer.stop()
        self.config.last_urls = self.url_edit.toPlainText().strip()
        update_app_config(
            last_urls=self.config.last_urls,
            save_dir=self.config.save_dir,
            thread_count=self.config.thread_count,
            bilibili_download_type=self.config.bilibili_download_type,
        )

    def flush_pending_save(self) -> None:
        """Persist a debounced edit right away, e.g. before closing the window."""
        if self.save_timer.isActive():
            self._save_config()

    def _parse_urls(self) -> list[str]:
        text = self.url_edit.toPlainText()
        if self._parsed_urls_cache is not None and self._parsed_urls_cache[0] == text:
            return self._parsed_urls_cache[1]
        candidates = (line.strip() for line in text.splitlines())
        urls = dedupe(item for item in candidates if looks_like_video_input(item))
        self._parsed_urls_cache = (text, urls)
        return urls

    def _on_text_changed(self) -> None:
        self._update_count()
        self.save_timer.start()

    def _update_count(self) -> None:
        self.count_label.setText(f"{len(self._parse_urls())} 个有效链接")

    def _clean_urls(self) -> None:
        urls = self._parse_urls()
        self.url_edit.setPlainText("\n".join(urls))
        self._set_status(f"已整理链接，当前保留 {len(urls)} 条。")

    def _choose_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", self.config.save_dir or str(Path.home()))
        if directory:
            self.config.save_dir = directory
            self.login_panel.set_save_dir(directory)
            self._refresh_dir_label()
            self._save_config()

    def _open_save_dir(self) -> None:
        if not open_directory(self.config.save_dir):
            MessageBox("提示", "当前保存目录不存在，请先重新选择。", self.window()).exec()

    def _open_example_link(self) -> None:
        if QDesktopServices.openUrl(QUrl(BILIBILI_STANDARD_LINK)):
            return
        MessageBox("提示", "无法打开链接，请检查系统默认浏览器设置。", self.window()).exec()

    def _copy_example_link(self) -> None:
        QApplication.clipboard().setText(BILIBILI_STANDARD_LINK)
        self._set_status("标准链接已复制，可以粘贴使用。")

    def _toggle_right_panel(self) -> None:
        self.right_panel_animation.stop()
        start_width = self.right_panel.width()
        self.right_panel_expanded = not self.right_panel_expanded
        if self.right_panel_expanded:
            self.right_panel.setVisible(True)
            self.right_panel_toggle.setIcon(FIF.CARE_RIGHT_SOLID)
            self.right_panel_toggle.setToolTip("收起右侧面板")
            target_width = 400
        else:
            self.right_panel_toggle.setIcon(FIF.CARE_LEFT_SOLID)
            self.right_panel_toggle.setToolTip("展开右侧面板")
            target_width = 0
        self.right_panel_animation.setStartValue(start_width)
        self.right_panel_animation.setEndValue(target_width)
        self.right_panel_animation.start()

    def _on_right_panel_animation_finished(self) -> None:
        if not self.right_panel_expanded:
            self.right_panel.setVisible(False)

    def _reset_task(self) -> None:
        if self.is_running():
            MessageBox("提示", "任务正在运行，请先停止再清空。", self.window()).exec()
            return
        self.url_edit.clear()
        self.table.setRowCount(0)
        self.failed_urls = []
        self.no_output_urls = []
        self._update_count()
        self._on_download_progress(0, 0, 0)

    def _on_thread_changed(self, value: str) -> None:
        try:
            self.config.thread_count = int(value)
        except ValueError:
            return
        self._refresh_engine_status()
        self._save_config()

    def _on_download_type_changed(self, download_type: str) -> None:
        if self.is_running():
            return
        self.config.bilibili_download_type = download_type
        self._refresh_download_type_ui()
        self._save_config()

    def _set_running_state(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.stop_btn.setText("停止任务")
        self.choose_dir_btn.setEnabled(not running)
        self.thread_combo.setEnabled(not running)
        self.download_type_segment.setEnabled(not running)
        self.clean_btn.setEnabled(not running)
        self.login_panel.set_download_running(running)

    def _start_download(self) -> None:
        if self.is_running():
            MessageBox("提示", "当前已有任务在运行，请先停止。", self.window()).exec()
            return
        urls = self._parse_urls()
        if not urls:
            MessageBox("提示", "请先粘贴至少一个有效视频链接。", self.window()).exec()
            return
        if not Path(self.config.save_dir).exists():
            MessageBox("提示", "保存目录不存在，请重新选择。", self.window()).exec()
            return
        if self.toolchain.bbdown is None:
            MessageBox("提示", "没有找到 BBDown.exe。", self.window()).exec()
            return
        if self.toolchain.ffmpeg is None and self.toolchain.mp4box is None:
            MessageBox("提示", "没有检测到 ffmpeg 或 mp4box，当前无法下载。", self.window()).exec()
            return

        self.flush_pending_save()
        self.failed_urls = []
        self.no_output_urls = []
        media_name = "视频" if self.config.bilibili_download_type == BILIBILI_VIDEO_DOWNLOAD else "音频"
        self._populate_tasks(urls)
        self._on_download_progress(0, len(urls), 0)
        self._set_status(f"准备下载{media_name}，共 {len(urls)} 条。")

        self.download_worker = DownloadWorkerThread(
            urls=urls,
            save_dir=self.config.save_dir,
            thread_count=self.config.thread_count,
            toolchain=self.toolchain,
            runtime_dir=RUNTIME_DIR,
            output_encoding=locale.getpreferredencoding(False) or "utf-8",
            download_type=self.config.bilibili_download_type,
        )
        self.download_worker.status.connect(self._set_status)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.task_progress.connect(self._on_task_progress)
        self.download_worker.task_status.connect(self._on_task_status)
        self.download_worker.finished_all.connect(self._on_download_finished)
        self.download_worker.start()
        self._set_running_state(True)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_download_progress(self, completed: int, total: int, active: int) -> None:
        percent = int(completed * 100 / total) if total else 0
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"进度 {completed}/{total} | {percent}% | 进行中 {active}")
        window = self.window()
        if window and total:
            window.setWindowTitle(f"BBDown - B站下载 {completed}/{total}")

    def _populate_tasks(self, urls: list[str]) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(urls))
        for row, url in enumerate(urls):
            id_item = QTableWidgetItem(bilibili_display_id(url))
            progress_item = QTableWidgetItem("0%")
            progress_item.setTextAlignment(Qt.AlignCenter)
            status_item = QTableWidgetItem("等待中")
            status_item.setForeground(QColor(BILIBILI_STATUS_COLORS["等待中"]))
            self.table.setItem(row, 0, id_item)
            self.table.setItem(row, 1, progress_item)
            self.table.setItem(row, 2, status_item)
        self.table.setUpdatesEnabled(True)

    def _on_task_progress(self, index: int, percent: int) -> None:
        progress_item = self.table.item(index - 1, 1)
        if progress_item is not None:
            progress_item.setText(f"{min(100, max(0, percent))}%")

    def _on_task_status(self, index: int, status: str, detail: str) -> None:
        row = index - 1
        status_item = self.table.item(row, 2)
        progress_item = self.table.item(row, 1)
        if status_item is not None:
            status_item.setText(f"{status}：{detail}" if status == "失败" and detail else status)
            status_item.setForeground(QColor(BILIBILI_STATUS_COLORS.get(status, "#a8a8a8")))
        if progress_item is not None:
            if status == "已完成":
                progress_item.setText("100%")
            elif status in {"失败", "已停止"}:
                progress_item.setText("--")

    def _on_download_finished(self, result: object) -> None:
        assert isinstance(result, DownloadBatchResult)
        self.download_worker = None
        self._set_running_state(False)
        if result.stopped:
            self._set_status(f"批量任务已停止，已完成 {result.completed}/{result.total}")
            return
        self.no_output_urls = dedupe(link.strip() for link in result.no_output_urls)
        self.failed_urls = dedupe(link.strip() for link in result.failed_urls)
        abnormal_urls = dedupe(self.no_output_urls + self.failed_urls)
        media_name = "视频" if self.config.bilibili_download_type == BILIBILI_VIDEO_DOWNLOAD else "音频"
        file_count = len(result.completed_files)
        no_output_count = len(self.no_output_urls)
        failed_count = len(self.failed_urls)
        if abnormal_urls:
            self.url_edit.setPlainText("\n".join(abnormal_urls))
            self._set_status(
                f"批量任务结束：生成 {file_count} 个{media_name}，"
                f"未产出 {no_output_count} 条，失败 {failed_count} 条"
            )
        else:
            self._set_status(f"批量任务完成，生成 {file_count} 个{media_name}")

    def stop(self) -> None:
        stopped_any = False
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.stop()
            stopped_any = True
        if self.login_panel.stop():
            stopped_any = True
        if stopped_any:
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("正在停止")
            self._set_status("正在停止任务，不再开始新任务...")

    def is_running(self) -> bool:
        return bool((self.download_worker and self.download_worker.isRunning()) or self.login_panel.is_running())
