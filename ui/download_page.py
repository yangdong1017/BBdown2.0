from __future__ import annotations

import locale
import os
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    MessageBox,
    PrimaryPushButton,
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
    save_app_config,
)
from core.models import AppConfig, DownloadBatchResult, LoginResult
from core.toolchain import resolve_toolchain
from core.workers import DownloadWorkerThread, LoginWorkerThread
from .widgets import CardFrame, ConsoleLog, TEXT_EDIT_STYLE


class DownloadPage(QWidget):
    request_transcribe = pyqtSignal(list, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("download")
        self.config: AppConfig = load_app_config()
        self.toolchain = resolve_toolchain()
        self.current_log_path = LOG_DIR / "launcher.log"
        self.download_worker: DownloadWorkerThread | None = None
        self.login_worker: LoginWorkerThread | None = None
        self.failed_urls: list[str] = []
        self.qr_timer = QTimer(self)
        self.qr_timer.timeout.connect(self._refresh_qr_preview)
        self.qr_mtime: float | None = None
        self._build_ui()
        self._apply_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        root.addWidget(TitleLabel("批量下载", self))
        self.engine_label = CaptionLabel(self)
        self.login_state_label = CaptionLabel(self)
        self.engine_label.setVisible(False)
        root.addWidget(self.login_state_label)

        split = QHBoxLayout()
        split.setSpacing(16)
        root.addLayout(split, 1)

        left = QVBoxLayout()
        left.setSpacing(14)
        split.addLayout(left, 5)

        content_card = CardFrame(self)
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(10)
        content_layout.addWidget(BodyLabel("视频链接", content_card))

        self.url_edit = TextEdit(content_card)
        self.url_edit.setPlaceholderText("在这里粘贴下载链接，一行一个 URL...")
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

        action_row = QHBoxLayout()
        self.start_btn = PrimaryPushButton("开始下载", content_card)
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = PushButton("停止任务", content_card)
        self.stop_btn.clicked.connect(self._stop_all_tasks)
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
        left.addWidget(content_card, 6)

        log_card = CardFrame(self)
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(18, 18, 18, 18)
        log_layout.setSpacing(8)
        log_layout.addWidget(BodyLabel("运行日志", log_card))
        self.console = ConsoleLog(log_card)
        log_layout.addWidget(self.console, 1)
        left.addWidget(log_card, 4)

        right = QVBoxLayout()
        right.setSpacing(14)
        split.addLayout(right, 3)

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
        right.addWidget(settings_card)

        login_card = CardFrame(self)
        login_layout = QVBoxLayout(login_card)
        login_layout.setContentsMargins(18, 18, 18, 18)
        login_layout.setSpacing(12)
        login_layout.addWidget(BodyLabel("登录二维码", login_card))

        login_mode_row = QHBoxLayout()
        self.login_mode_combo = ComboBox(login_card)
        self.login_mode_combo.addItems(["WEB 登录", "TV 登录"])
        self.login_btn = PushButton("执行登录", login_card)
        self.login_btn.clicked.connect(self._start_login)
        login_mode_row.addWidget(self.login_mode_combo)
        login_mode_row.addWidget(self.login_btn)
        login_layout.addLayout(login_mode_row)

        self.qr_status_label = CaptionLabel("点击“执行登录”后会在这里显示二维码。", login_card)
        self.qr_status_label.setWordWrap(True)
        self.qr_status_label.setVisible(False)

        self.qr_image_label = BodyLabel("暂无二维码", login_card)
        self.qr_image_label.setAlignment(Qt.AlignCenter)
        self.qr_image_label.setMinimumHeight(260)
        self.qr_image_label.setStyleSheet(
            "QLabel { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }"
        )
        login_layout.addWidget(self.qr_image_label)
        right.addWidget(login_card, 1)

        self.status_label = CaptionLabel("就绪", self)
        root.addWidget(self.status_label)

    def _apply_state(self) -> None:
        self.url_edit.setPlainText(self.config.last_urls)
        self.thread_combo.setCurrentText(str(self.config.thread_count))
        self._refresh_engine_status()
        self._refresh_login_status()
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

    def _refresh_login_status(self) -> None:
        base_dir = self.toolchain.bbdown.parent if self.toolchain.bbdown else Path.cwd()
        web_state = "已登录" if (base_dir / "BBDown.data").exists() else "未登录"
        tv_state = "已登录" if (base_dir / "BBDownTV.data").exists() else "未登录"
        self.login_state_label.setText(f"登录状态: WEB {web_state} | TV {tv_state}")

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
        save_app_config(self.config)

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
        self._update_count()

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
        self.choose_dir_btn.setEnabled(not running)
        self.thread_combo.setEnabled(not running)
        self.clean_btn.setEnabled(not running)

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
        self._new_session_log("download_batch")
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
        self.download_worker.finished_all.connect(self._on_download_finished)
        self.download_worker.start()
        self._set_running_state(True)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_download_finished(self, result: object) -> None:
        assert isinstance(result, DownloadBatchResult)
        self.download_worker = None
        self._set_running_state(False)
        if result.stopped:
            self._append_log("warn", f"批量任务已停止，已完成 {result.completed}/{result.total}。")
            self._set_status(f"批量任务已停止，已完成 {result.completed}/{result.total}")
            return
        if result.failed_urls:
            self.failed_urls = result.failed_urls
            self._append_log("warn", f"批量任务结束，成功 {result.completed} 个，失败 {len(result.failed_urls)} 个。")
            for item in result.failed_urls:
                self._append_log("fail", f"失败链接: {item}")
            self._set_status(f"批量任务结束，成功 {result.completed}/{result.total}，失败 {len(result.failed_urls)}")
        else:
            self._append_log("ok", f"批量任务完成，共完成 {result.completed} 个链接。")
            self._set_status(f"批量任务完成，共完成 {result.completed}/{result.total}")

        if result.completed_files:
            message = MessageBox(
                "下载完成",
                f"本次生成 {len(result.completed_files)} 个音频文件，是否批量转文字？",
                self.window(),
            )
            if message.exec():
                self.request_transcribe.emit(result.completed_files, self.config.save_dir)

    def _start_login(self) -> None:
        if self.is_running():
            MessageBox("提示", "请先停止当前下载任务，再执行登录。", self.window()).exec()
            return
        if self.login_worker and self.login_worker.isRunning():
            MessageBox("提示", "登录流程已经在运行。", self.window()).exec()
            return
        if self.toolchain.bbdown is None:
            MessageBox("提示", "没有找到 BBDown.exe。", self.window()).exec()
            return

        self._new_session_log("login")
        self._clear_qr_preview()
        mode = "web" if "WEB" in self.login_mode_combo.currentText() else "tv"
        self.qr_status_label.setText("正在获取登录二维码...")
        self._append_log("info", f"开始执行 {'WEB 登录' if mode == 'web' else 'TV 登录'}。")

        self.login_worker = LoginWorkerThread(
            mode=mode,
            toolchain=self.toolchain,
            runtime_dir=RUNTIME_DIR,
            log_encoding=locale.getpreferredencoding(False) or "utf-8",
        )
        self.login_worker.log.connect(self._append_log)
        self.login_worker.status.connect(self._set_status)
        self.login_worker.finished_one.connect(self._on_login_finished)
        self.login_worker.start()
        self.qr_timer.start(500)

    def _on_login_finished(self, result: object) -> None:
        assert isinstance(result, LoginResult)
        self.login_worker = None
        self.qr_timer.stop()
        self._refresh_login_status()
        if result.stopped:
            self.qr_status_label.setText("登录流程已停止。")
            self._append_log("warn", "登录流程已停止。")
        elif result.return_code == 0:
            self.qr_status_label.setText("登录流程已结束，如已确认扫码，上方状态通常会显示为已登录。")
            self._append_log("ok", "登录流程完成。")
        else:
            self.qr_status_label.setText(f"登录流程结束，退出码 {result.return_code}")
            self._append_log("fail", f"登录流程结束，退出码: {result.return_code}")

    def _refresh_qr_preview(self) -> None:
        if not (self.login_worker and self.login_worker.isRunning()):
            return
        for qr_path in (RUNTIME_DIR / "qrcode.png", Path(self.config.save_dir).parent / "qrcode.png", Path.cwd() / "qrcode.png"):
            if not qr_path.exists():
                continue
            mtime = qr_path.stat().st_mtime
            if self.qr_mtime == mtime:
                return
            pixmap = QPixmap(str(qr_path))
            if pixmap.isNull():
                continue
            scaled = pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_image_label.setPixmap(scaled)
            self.qr_image_label.setText("")
            self.qr_status_label.setText("二维码已生成，请用哔哩哔哩 App 扫码并确认。")
            self.qr_mtime = mtime
            return

    def _clear_qr_preview(self) -> None:
        for qr_path in (RUNTIME_DIR / "qrcode.png", Path.cwd() / "qrcode.png"):
            if qr_path.exists():
                try:
                    qr_path.unlink()
                except OSError:
                    pass
        self.qr_image_label.clear()
        self.qr_image_label.setText("暂无二维码")
        self.qr_status_label.setText("点击“执行登录”后会在这里显示二维码。")
        self.qr_mtime = None

    def _stop_all_tasks(self) -> None:
        stopped_any = False
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.stop()
            stopped_any = True
        if self.login_worker and self.login_worker.isRunning():
            self.login_worker.stop()
            stopped_any = True
        if stopped_any:
            self._append_log("warn", "正在停止当前任务...")
            self._set_status("正在停止任务...")

    def is_running(self) -> bool:
        return bool((self.download_worker and self.download_worker.isRunning()) or (self.login_worker and self.login_worker.isRunning()))
