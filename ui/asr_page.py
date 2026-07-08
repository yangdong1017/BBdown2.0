from __future__ import annotations

import subprocess
import sys
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
from qfluentwidgets import BodyLabel, ComboBox, MessageBox, PrimaryPushButton, PushButton, TableWidget, TitleLabel
from qfluentwidgets import ProgressBar

from core.config import (
    ASR_CONCURRENCY_OPTIONS,
    ASR_ENGINE_OPTIONS,
    ASR_FORMAT_OPTIONS,
    ASR_MODE_OPTIONS,
    DOUBAO_ENGINE_NAME,
    DOUBAO_ASR_CONCURRENCY_OPTIONS,
    LOCAL_FILE_ASR_ENGINE_OPTIONS,
    load_doubao_api_key,
    load_app_config,
    save_app_config,
)
from core.asr_file_worker import ASRWorkerThread
from core.media import MEDIA_EXTENSIONS, is_media
from core.toolchain import resolve_toolchain
from core.url_asr_worker import UrlASRBatchResult, UrlASRWorkerThread, default_url_output_dir
from core.url_audio import extract_audio_urls, extract_douyin_share_urls
from .widgets import ConsoleLog, TEXT_EDIT_STYLE


STATUS_COLORS = {
    "处理中": "#e5b84a",
    "已完成": "#7fd26f",
    "跳过": "#6aaee6",
    "失败": "#ff6a5c",
    "未处理": "#a8a8a8",
}

DOUYIN_ASR_MODE = "抖音音频链接转文字"


class ASRPage(QWidget):
    request_download_dir = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("asr")
        self.config = load_app_config()
        self.toolchain = resolve_toolchain()
        self.worker: ASRWorkerThread | None = None
        self.url_worker: UrlASRWorkerThread | None = None
        self.row_index_map: list[int] = []
        self._build_ui()
        self._apply_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.addWidget(TitleLabel("批量转文字", self))
        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(list(ASR_MODE_OPTIONS))
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        title_row.addWidget(self.mode_combo)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        options = QHBoxLayout()
        options.addWidget(BodyLabel("ASR 接口:", self))
        self.engine_combo = ComboBox(self)
        self.engine_combo.addItems(list(ASR_ENGINE_OPTIONS))
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        options.addWidget(self.engine_combo)
        options.addSpacing(12)

        options.addWidget(BodyLabel("输出格式:", self))
        self.format_combo = ComboBox(self)
        self.format_combo.addItems(list(ASR_FORMAT_OPTIONS))
        options.addWidget(self.format_combo)
        options.addSpacing(12)

        options.addWidget(BodyLabel("并发:", self))
        self.concurrency_combo = ComboBox(self)
        self.concurrency_combo.addItems([str(value) for value in ASR_CONCURRENCY_OPTIONS])
        options.addWidget(self.concurrency_combo)
        options.addStretch(1)
        layout.addLayout(options)

        out_row = QHBoxLayout()
        self.out_dir_btn = PushButton("选择输出目录", self)
        self.out_dir_btn.clicked.connect(self._choose_out_dir)
        self.out_dir_label = BodyLabel(self)
        self.out_dir_label.setStyleSheet("color: #9a9a9a;")
        out_row.addWidget(self.out_dir_btn)
        out_row.addWidget(self.out_dir_label, 1)
        layout.addLayout(out_row)

        file_row = QHBoxLayout()
        self.add_files_btn = PushButton("选择音视频文件", self)
        self.add_files_btn.clicked.connect(self._select_files)
        self.add_folder_btn = PushButton("选择文件夹", self)
        self.add_folder_btn.clicked.connect(self._select_folder)
        self.use_download_dir_btn = PushButton("使用下载目录", self)
        self.use_download_dir_btn.clicked.connect(self.request_download_dir.emit)
        self.clear_btn = PushButton("清空输入", self)
        self.clear_btn.clicked.connect(self._clear_files)
        file_row.addWidget(self.add_files_btn)
        file_row.addWidget(self.add_folder_btn)
        file_row.addWidget(self.use_download_dir_btn)
        file_row.addWidget(self.clear_btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)

        self.url_edit = QPlainTextEdit(self)
        self.url_edit.setPlaceholderText("粘贴抖音 mp3/wav 音频直链，一行一个；也可以粘贴包含音频直链的整段文本。")
        self.url_edit.setMinimumHeight(76)
        self.url_edit.setMaximumHeight(110)
        self.url_edit.setStyleSheet(TEXT_EDIT_STYLE)
        layout.addWidget(self.url_edit)

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

        progress_row = QHBoxLayout()
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label = BodyLabel("进度 0/0", self)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_label)
        layout.addLayout(progress_row)

        action_row = QHBoxLayout()
        self.start_btn = PrimaryPushButton("开始转文字", self)
        self.start_btn.clicked.connect(self._start)
        self.open_out_btn = PushButton("打开输出目录", self)
        self.open_out_btn.clicked.connect(self._open_out)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.open_out_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.log = ConsoleLog(self)
        self.log.setMinimumHeight(150)
        layout.addWidget(self.log, 0)
        self.setAcceptDrops(True)

    def _apply_state(self) -> None:
        self.mode_combo.setCurrentText(self.config.asr_mode)
        self._sync_engine_options(self.mode_combo.currentText())
        if self.config.asr_engine in self._current_engine_options():
            self.engine_combo.setCurrentText(self.config.asr_engine)
        self.format_combo.setCurrentText(self.config.asr_format)
        self.concurrency_combo.setCurrentText(str(self.config.asr_concurrency))
        self._on_engine_changed(self.engine_combo.currentText())
        self._refresh_out_label()

    def _save_state(self) -> None:
        self.config.asr_mode = self.mode_combo.currentText()
        self.config.asr_engine = self.engine_combo.currentText()
        self.config.asr_format = self.format_combo.currentText()
        self.config.asr_concurrency = int(self.concurrency_combo.currentText())
        save_app_config(self.config)

    def _is_douyin_mode(self) -> bool:
        return self.mode_combo.currentText() == DOUYIN_ASR_MODE

    def _on_mode_changed(self, mode: str) -> None:
        is_douyin = mode == DOUYIN_ASR_MODE
        self._sync_engine_options(mode)
        self.add_files_btn.setVisible(not is_douyin)
        self.add_folder_btn.setVisible(not is_douyin)
        self.use_download_dir_btn.setVisible(not is_douyin)
        self.table.setVisible(not is_douyin)
        self.url_edit.setVisible(is_douyin)
        self.clear_btn.setText("清空链接" if is_douyin else "清空列表")
        self.config.asr_mode = mode
        self._refresh_out_label()

    def _current_engine_options(self) -> tuple[str, ...]:
        if self._is_douyin_mode():
            return ASR_ENGINE_OPTIONS
        return LOCAL_FILE_ASR_ENGINE_OPTIONS

    def _sync_engine_options(self, mode: str) -> None:
        options = ASR_ENGINE_OPTIONS if mode == DOUYIN_ASR_MODE else LOCAL_FILE_ASR_ENGINE_OPTIONS
        current = self.engine_combo.currentText() or self.config.asr_engine
        self.engine_combo.blockSignals(True)
        self.engine_combo.clear()
        self.engine_combo.addItems(list(options))
        self.engine_combo.setCurrentText(current if current in options else options[0])
        self.engine_combo.blockSignals(False)
        self._on_engine_changed(self.engine_combo.currentText())

    def _on_engine_changed(self, engine_name: str) -> None:
        is_doubao = engine_name == DOUBAO_ENGINE_NAME
        self._sync_concurrency_options(engine_name)
        if is_doubao:
            self.format_combo.setCurrentText("txt")
        self.format_combo.setEnabled(not is_doubao)

    def _sync_concurrency_options(self, engine_name: str) -> None:
        options = DOUBAO_ASR_CONCURRENCY_OPTIONS if engine_name == DOUBAO_ENGINE_NAME else ASR_CONCURRENCY_OPTIONS
        current = self.concurrency_combo.currentText() or str(self.config.asr_concurrency)
        self.concurrency_combo.blockSignals(True)
        self.concurrency_combo.clear()
        self.concurrency_combo.addItems([str(value) for value in options])
        self.concurrency_combo.setCurrentText(current if int(current or 0) in options else str(options[0]))
        self.concurrency_combo.blockSignals(False)

    def _refresh_out_label(self) -> None:
        if self.config.asr_output_dir:
            text = self.config.asr_output_dir
        elif self._is_douyin_mode():
            text = f"默认: {default_url_output_dir()}"
        else:
            text = "默认: 与源文件同目录"
        self.out_dir_label.setText(text)

    def _choose_out_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            self.config.asr_output_dir or self.config.save_dir or str(Path.home()),
        )
        if directory:
            self.config.asr_output_dir = directory
            save_app_config(self.config)
            self._refresh_out_label()

    def _open_out(self) -> None:
        target = self.config.asr_output_dir
        if not target and not self._is_douyin_mode() and self.table.rowCount() > 0:
            item = self.table.item(0, 0)
            path = item.data(Qt.UserRole) if item else ""
            target = str(Path(path).parent) if path else ""
        if not target and self._is_douyin_mode():
            target = str(default_url_output_dir())
        if not target or not Path(target).is_dir():
            return
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])

    def _select_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择音视频文件",
            self.config.save_dir or "",
            "音视频文件 (*.mp3 *.wav *.m4a *.flac *.aac *.ogg *.wma *.mp4 *.mkv *.flv *.mov *.avi *.wmv *.ts *.webm *.rmvb);;所有文件 (*)",
        )
        self.add_files(files)

    def _select_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择文件夹", self.config.save_dir or "")
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
            existing.add(resolved)
            added += 1
        if added:
            self.log.log("info", f"添加 {added} 个文件")

    def _clear_files(self) -> None:
        if self._is_douyin_mode():
            self.url_edit.clear()
        else:
            self.table.setRowCount(0)
        self._set_asr_progress(0, 0)

    def _collect_unprocessed(self) -> list[tuple[int, str]]:
        files: list[tuple[int, str]] = []
        for row in range(self.table.rowCount()):
            status_item = self.table.item(row, 2)
            name_item = self.table.item(row, 0)
            if not status_item or not name_item:
                continue
            if status_item.text() in ("未处理", "失败"):
                files.append((row, name_item.data(Qt.UserRole)))
        return files

    def _start(self) -> None:
        if self.is_running():
            self.stop()
            return

        if self._is_douyin_mode():
            if self.engine_combo.currentText() == DOUBAO_ENGINE_NAME and not load_doubao_api_key():
                MessageBox("提示", "请先到左下角设置填写豆包 API Key。", self.window()).exec()
                return
            url_pending = extract_audio_urls(self.url_edit.toPlainText())
            if not url_pending:
                share_urls = extract_douyin_share_urls(self.url_edit.toPlainText())
                if share_urls:
                    MessageBox(
                        "提示",
                        "检测到的是抖音视频分享链接，不是 mp3/wav 音频直链，当前不能直接转写。请粘贴抖音音频直链后再开始。",
                        self.window(),
                    ).exec()
                else:
                    MessageBox("提示", "没有检测到可转写的抖音音频直链。", self.window()).exec()
                return
            self._start_url_asr(url_pending)
            return

        pending = self._collect_unprocessed()
        if not pending:
            MessageBox("提示", "没有需要处理的音视频文件。", self.window()).exec()
            return

        self._start_file_asr(pending)

    def _start_file_asr(self, pending: list[tuple[int, str]]) -> None:
        self._save_state()
        self.row_index_map = [row for row, _ in pending]
        files = [path for _, path in pending]
        self._set_asr_progress(0, len(files))
        ffmpeg_path = str(self.toolchain.ffmpeg) if self.toolchain.ffmpeg else None
        self.log.log(
            "info",
            f"开始转文字: {len(files)} 个文件 | {self.config.asr_engine} | {self.config.asr_format} | 并发 {self.config.asr_concurrency}",
        )
        if ffmpeg_path is None:
            self.log.log("warn", "未检测到 ffmpeg，视频文件无法自动转音频。")

        self.worker = ASRWorkerThread(
            files=files,
            engine_name=self.config.asr_engine,
            export_format=self.config.asr_format,
            concurrency=self.config.asr_concurrency,
            out_dir=self.config.asr_output_dir,
            ffmpeg_path=ffmpeg_path,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.file_status.connect(self._on_file_status)
        self.worker.count.connect(self._on_count)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()
        self.start_btn.setEnabled(True)
        self.start_btn.setText("停止")

    def _start_url_asr(self, urls: list[str]) -> None:
        self._save_state()
        self.row_index_map = []
        self._set_asr_progress(0, len(urls))
        self.log.log(
            "info",
            f"开始音频链接转文字: {len(urls)} 条 | {self.config.asr_engine} | {self.config.asr_format} | 并发 {self.config.asr_concurrency}",
        )

        self.url_worker = UrlASRWorkerThread(
            urls=urls,
            engine_name=self.config.asr_engine,
            export_format=self.config.asr_format,
            concurrency=self.config.asr_concurrency,
            out_dir=self.config.asr_output_dir,
        )
        self.url_worker.progress.connect(self._on_url_progress)
        self.url_worker.count.connect(self._on_url_count)
        self.url_worker.finished_all.connect(self._on_url_finished)
        self.url_worker.start()
        self.start_btn.setEnabled(True)
        self.start_btn.setText("停止")

    def stop(self) -> None:
        stopped = False
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            stopped = True
        if self.url_worker and self.url_worker.isRunning():
            self.url_worker.stop()
            stopped = True
        if stopped:
            self.start_btn.setEnabled(False)
            self.start_btn.setText("正在停止")
            self.progress_label.setText(self.progress_label.text().replace("进度", "停止中", 1))
            self.log.log("warn", "正在停止：不会再开始新任务，正在等待当前任务结束。")

    def _on_progress(self, index: int, path: str, status: str, message: str) -> None:
        level = {"ok": "ok", "skip": "skip", "fail": "fail"}.get(status, "info")
        prefix = {"ok": "OK", "skip": "SKIP", "fail": "FAIL"}.get(status, "INFO")
        self.log.log(level, f"[{prefix}] {message}")

    def _on_file_status(self, index: int, status: str) -> None:
        row = self.row_index_map[index] if index < len(self.row_index_map) else index
        if 0 <= row < self.table.rowCount():
            item = QTableWidgetItem(status)
            item.setForeground(QColor(STATUS_COLORS.get(status, "#cccccc")))
            self.table.setItem(row, 2, item)

    def _on_count(self, ok: int, skip: int, fail: int, total: int, filename: str) -> None:
        done = ok + skip + fail
        self._set_asr_progress(done, total)
        window = self.window()
        if window:
            window.setWindowTitle(f"BBDown - 转文字 {done}/{total}")

    def _on_finished(self, summary: str) -> None:
        self.log.log("info", f"--- {summary} ---")
        self.start_btn.setEnabled(True)
        self.start_btn.setText("开始转文字")
        window = self.window()
        if window:
            window.setWindowTitle(f"BBDown - {summary}")
        self.worker = None

    def _on_url_progress(self, index: int, url: str, status: str, message: str) -> None:
        level = {"ok": "ok", "skip": "skip", "fail": "fail"}.get(status, "info")
        prefix = {"ok": "OK", "skip": "SKIP", "fail": "FAIL"}.get(status, "INFO")
        self.log.log(level, f"[{prefix}] {message}")

    def _on_url_count(self, ok: int, skip: int, fail: int, total: int, filename: str) -> None:
        done = ok + skip + fail
        self._set_asr_progress(done, total)
        window = self.window()
        if window:
            window.setWindowTitle(f"BBDown - 音频转文字 {done}/{total}")

    def _set_asr_progress(self, done: int, total: int) -> None:
        percent = int(done * 100 / total) if total else 0
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"进度 {done}/{total} | {percent}%")

    def _on_url_finished(self, result: UrlASRBatchResult) -> None:
        self.log.log("info", f"--- {result.summary} ---")
        if result.failed_urls:
            self.url_edit.setPlainText("\n".join(result.failed_urls))
            self.log.log("warn", f"已把 {len(result.failed_urls)} 条失败链接留在输入框，可直接重试。")
        else:
            self.url_edit.clear()
        self.start_btn.setEnabled(True)
        self.start_btn.setText("开始转文字")
        window = self.window()
        if window:
            window.setWindowTitle(f"BBDown - {result.summary}")
        self.url_worker = None

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        files: list[str] = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                files.extend(str(item) for item in path.rglob("*") if item.is_file() and is_media(item))
            elif path.is_file() and is_media(path):
                files.append(str(path))
        self.add_files(files)

    def is_running(self) -> bool:
        return bool(
            (self.worker and self.worker.isRunning())
            or (self.url_worker and self.url_worker.isRunning())
        )
