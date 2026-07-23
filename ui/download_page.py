from __future__ import annotations

import locale
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    TextEdit,
    TitleLabel,
)

from core.commands import looks_like_video_input
from core.config import (
    AUDIO_FILE_PATTERN,
    LOG_DIR,
    RUNTIME_DIR,
    THREAD_OPTIONS,
    load_app_config,
    update_app_config,
)
from core.bilibili_workers import DownloadWorkerThread
from core.models import AppConfig, DownloadBatchResult
from core.toolchain import resolve_toolchain
from .bilibili_login_panel import BilibiliLoginPanel
from .widgets import CardFrame, ConsoleLog, TEXT_EDIT_STYLE


class DownloadPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("download")
        self.config: AppConfig = load_app_config()
        self.toolchain = resolve_toolchain()
        self.current_log_path = LOG_DIR / "launcher.log"
        self.download_worker: DownloadWorkerThread | None = None
        self.failed_urls: list[str] = []
        self.no_output_urls: list[str] = []
        self._build_ui()
        self._apply_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)
        root.addWidget(TitleLabel("B站下载", self))

        self.engine_label = CaptionLabel(self)
        self.login_state_label = CaptionLabel(self)
        self.engine_label.setVisible(False)
        root.addWidget(self.login_state_label)

        split = QHBoxLayout()
        split.setSpacing(16)
        root.addLayout(split, 1)

        left = QVBoxLayout()
        left.setSpacing(14)
        left.addWidget(self._build_download_card(), 6)
        left.addWidget(self._build_log_card(), 4)
        split.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(self._build_settings_card())
        right.addWidget(self._build_login_panel(), 1)
        split.addLayout(right, 3)

        self.status_label = CaptionLabel("就绪", self)
        root.addWidget(self.status_label)

    def _build_download_card(self) -> CardFrame:
        content_card = CardFrame(self)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(10)
        content_layout.addWidget(BodyLabel("视频链接", content_card))

        self.url_edit = TextEdit(content_card)
        self.url_edit.setPlaceholderText("在这里粘贴 B站 视频链接，一行一个 URL...")
        self.url_edit.setMinimumHeight(260)
        self.url_edit.setStyleSheet(TEXT_EDIT_STYLE)
        self.url_edit.textChanged.connect(self._update_count)
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
        self.log_btn = PushButton("查看日志", content_card)
        self.log_btn.clicked.connect(self._open_log_file)
        self.reset_btn = PushButton("清空任务", content_card)
        self.reset_btn.clicked.connect(self._reset_task)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addWidget(self.log_btn)
        action_row.addWidget(self.reset_btn)
        action_row.addStretch(1)
        content_layout.addLayout(action_row)
        return content_card

    def _build_log_card(self) -> CardFrame:
        log_card = CardFrame(self)
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(18, 18, 18, 18)
        log_layout.setSpacing(8)
        log_layout.addWidget(BodyLabel("运行日志", log_card))
        self.console = ConsoleLog(log_card)
        log_layout.addWidget(self.console, 1)
        return log_card

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

        self.thread_hint_label = CaptionLabel(settings_card)
        self.thread_hint_label.setWordWrap(True)
        settings_layout.addWidget(self.thread_hint_label)
        settings_layout.addWidget(CaptionLabel(f"默认输出格式为 {AUDIO_FILE_PATTERN}.m4a", settings_card))
        return settings_card

    def _build_login_panel(self) -> BilibiliLoginPanel:
        self.login_panel = BilibiliLoginPanel(
            toolchain=self.toolchain,
            runtime_dir=RUNTIME_DIR,
            save_dir=self.config.save_dir,
            parent=self,
        )
        self.login_panel.log.connect(self._append_log)
        self.login_panel.status.connect(self._set_status)
        self.login_panel.session_started.connect(self._new_session_log)
        self.login_panel.login_state_changed.connect(self.login_state_label.setText)
        return self.login_panel

    def _apply_state(self) -> None:
        self.url_edit.setPlainText(self.config.last_urls)
        self.thread_combo.setCurrentText(str(self.config.thread_count))
        self._refresh_engine_status()
        self.login_panel.refresh_login_status()
        self._refresh_dir_label()
        self._refresh_thread_hint()
        self._set_running_state(False)
        self._update_count()

    def _refresh_engine_status(self) -> None:
        state = "已连接" if self.toolchain.bbdown else "未找到"
        ffmpeg_name = self.toolchain.ffmpeg.name if self.toolchain.ffmpeg else "未检测到"
        aria2_desc = f"{self.config.thread_count}线程/任务" if self.toolchain.aria2c else "未检测到"
        self.engine_label.setText(
            f"引擎: {self.toolchain.bbdown or '未找到'} | 状态: {state} | ffmpeg: {ffmpeg_name} | aria2c: {aria2_desc} | 批量并发: {self.config.thread_count}"
        )

    def _refresh_dir_label(self) -> None:
        display = self.config.save_dir
        if len(display) > 58:
            display = "..." + display[-55:]
        suffix = "" if Path(self.config.save_dir).exists() else " (目录不存在)"
        self.dir_label.setText(f"保存到: {display}{suffix}")

    def _refresh_thread_hint(self) -> None:
        self.thread_hint_label.setText(
            f"当前 {self.config.thread_count} 并发。它同时控制批量并发数，以及每个任务内部的 aria2c 下载并发。"
        )

    def _save_config(self) -> None:
        self.config.last_urls = self.url_edit.toPlainText().strip()
        update_app_config(
            last_urls=self.config.last_urls,
            save_dir=self.config.save_dir,
            thread_count=self.config.thread_count,
        )

    def _append_log(self, level: str, message: str) -> None:
        self.console.log(level, message)
        self.current_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.current_log_path.open("a", encoding="utf-8") as fh:
            fh.write(message + "\n")

    def _new_session_log(self, name: str) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.current_log_path = LOG_DIR / f"{Path.cwd().stem}_{name}.log"
        self.console.clear()

    def _parse_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for line in self.url_edit.toPlainText().splitlines():
            item = line.strip()
            if not looks_like_video_input(item):
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            urls.append(item)
        return urls

    def _update_count(self) -> None:
        self.count_label.setText(f"{len(self._parse_urls())} 个有效链接")
        self._save_config()

    def _clean_urls(self) -> None:
        urls = self._parse_urls()
        self.url_edit.setPlainText("\n".join(urls))
        self._append_log("info", f"已整理链接列表，当前保留 {len(urls)} 个有效链接。")

    def _choose_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", self.config.save_dir or str(Path.home()))
        if directory:
            self.config.save_dir = directory
            self.login_panel.set_save_dir(directory)
            self._refresh_dir_label()
            self._save_config()

    def _open_save_dir(self) -> None:
        path = Path(self.config.save_dir)
        if not path.exists():
            MessageBox("提示", "当前保存目录不存在，请先重新选择。", self.window()).exec()
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _open_log_file(self) -> None:
        target = self.current_log_path if self.current_log_path.exists() else LOG_DIR
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def _reset_task(self) -> None:
        if self.is_running():
            MessageBox("提示", "任务正在运行，请先停止再清空。", self.window()).exec()
            return
        self.url_edit.clear()
        self.console.clear()
        self.failed_urls = []
        self.no_output_urls = []
        self._update_count()
        self._on_download_progress(0, 0, 0)

    def _on_thread_changed(self, value: str) -> None:
        try:
            self.config.thread_count = int(value)
        except ValueError:
            return
        self._refresh_thread_hint()
        self._refresh_engine_status()
        self._save_config()

    def _set_running_state(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.stop_btn.setText("停止任务")
        self.choose_dir_btn.setEnabled(not running)
        self.thread_combo.setEnabled(not running)
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

        self.failed_urls = []
        self.no_output_urls = []
        self._new_session_log("download_batch")
        self._on_download_progress(0, len(urls), 0)
        self._append_log("info", f"准备开始批量下载，线程设置 {self.config.thread_count}。")

        self.download_worker = DownloadWorkerThread(
            urls=urls,
            save_dir=self.config.save_dir,
            thread_count=self.config.thread_count,
            toolchain=self.toolchain,
            runtime_dir=RUNTIME_DIR,
            log_encoding=locale.getpreferredencoding(False) or "utf-8",
        )
        self.download_worker.log.connect(self._append_log)
        self.download_worker.status.connect(self._set_status)
        self.download_worker.progress.connect(self._on_download_progress)
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

    def _on_download_finished(self, result: object) -> None:
        assert isinstance(result, DownloadBatchResult)
        self.download_worker = None
        self._set_running_state(False)
        if result.stopped:
            self._append_log("warn", f"批量任务已停止，已完成 {result.completed}/{result.total}。")
            self._set_status(f"批量任务已停止，已完成 {result.completed}/{result.total}")
            return
        self.no_output_urls = self._dedupe_links(result.no_output_urls)
        self.failed_urls = self._dedupe_links(result.failed_urls)
        abnormal_urls = self._dedupe_links(self.no_output_urls + self.failed_urls)
        file_count = len(result.completed_files)
        no_output_count = len(self.no_output_urls)
        failed_count = len(self.failed_urls)
        summary = (
            f"批量任务结束：生成音频 {file_count} 个，成功链接 {result.completed} 条，"
            f"未产出音频 {no_output_count} 条，失败 {failed_count} 条。"
        )
        self._append_log("warn" if abnormal_urls else "ok", summary)
        self._append_link_section("未产出音频链接", self.no_output_urls, "warn")
        self._append_link_section("失败链接", self.failed_urls, "fail")

        if abnormal_urls:
            self.url_edit.setPlainText("\n".join(abnormal_urls))
            self._append_log("warn", f"已将 {len(abnormal_urls)} 条异常链接填回输入框，可再次点击“开始下载”继续处理。")
            self._set_status(
                f"批量任务结束，生成 {file_count} 个音频，剩余异常 {len(abnormal_urls)} 条"
            )
        else:
            self._set_status(f"批量任务完成，生成 {file_count} 个音频")

    def _dedupe_links(self, links: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for link in links:
            key = link.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(link.strip())
        return result

    def _append_link_section(self, title: str, links: list[str], level: str) -> None:
        self._append_log(level if links else "info", f"{title}:")
        if links:
            for link in links:
                self._append_log(level, link)
        else:
            self._append_log("info", "无")

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
            self._append_log("warn", "正在停止：不会再开始新任务，正在结束当前任务。")
            self._set_status("正在停止任务，不再开始新任务...")

    def is_running(self) -> bool:
        return bool((self.download_worker and self.download_worker.isRunning()) or self.login_panel.is_running())
