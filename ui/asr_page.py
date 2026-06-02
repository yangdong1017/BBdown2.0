from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
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
from qfluentwidgets import BodyLabel, ComboBox, MessageBox, PrimaryPushButton, PushButton, TableWidget, TitleLabel

from bk_asr import BcutASR, JianYingASR, KuaiShouASR
from core.config import ASR_CONCURRENCY_OPTIONS, ASR_ENGINE_OPTIONS, ASR_FORMAT_OPTIONS, load_app_config, save_app_config
from core.media import MEDIA_EXTENSIONS, convert_to_mp3, is_audio, is_media
from core.toolchain import resolve_toolchain
from .widgets import ConsoleLog


ENGINE_MAP = {
    "必剪": BcutASR,
    "剪映": JianYingASR,
    "快手": KuaiShouASR,
}

STATUS_COLORS = {
    "处理中": "#e5b84a",
    "已完成": "#7fd26f",
    "跳过": "#6aaee6",
    "失败": "#ff6a5c",
    "未处理": "#a8a8a8",
}


class ASRWorkerThread(QThread):
    progress = pyqtSignal(int, str, str, str)
    file_status = pyqtSignal(int, str)
    count = pyqtSignal(int, int, int, int, str)
    finished_all = pyqtSignal(str)

    def __init__(
        self,
        files: list[str],
        engine_name: str,
        export_format: str,
        concurrency: int,
        out_dir: str,
        ffmpeg_path: str | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.files = files
        self.engine_name = engine_name
        self.export_format = export_format.lower()
        self.concurrency = max(1, int(concurrency))
        self.out_dir = out_dir
        self.ffmpeg_path = ffmpeg_path
        self.stop_flag = threading.Event()

    def stop(self) -> None:
        self.stop_flag.set()

    def _process_one(self, index: int, path: str) -> tuple[int, str, str, str]:
        if self.stop_flag.is_set():
            return index, path, "stopped", "已停止"

        source = Path(path)
        out_dir = Path(self.out_dir) if self.out_dir else source.parent
        out_path = out_dir / f"{source.stem}.{self.export_format}"

        if out_path.exists() and out_path.stat().st_size > 0:
            return index, path, "skip", f"{source.name} -> 已存在"

        self.file_status.emit(index, "处理中")

        audio_path = source
        temp_audio: str | None = None
        if not is_audio(source):
            fd, temp_audio = tempfile.mkstemp(suffix=".mp3", prefix=f"asr_{source.stem[:40]}_")
            os.close(fd)
            if not convert_to_mp3(source, temp_audio, self.ffmpeg_path):
                try:
                    os.remove(temp_audio)
                except OSError:
                    pass
                return index, path, "fail", f"{source.name}: ffmpeg 转音频失败"
            audio_path = Path(temp_audio)

        try:
            engine_cls = ENGINE_MAP[self.engine_name]
            result = engine_cls(str(audio_path), use_cache=True).run()
            if self.export_format == "srt":
                text = result.to_srt()
            elif self.export_format == "ass":
                text = result.to_ass()
            else:
                text = result.to_txt()
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            return index, path, "ok", f"{source.name} -> {out_path.name}"
        except Exception as exc:
            return index, path, "fail", f"{source.name}: {exc}"
        finally:
            if temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except OSError:
                    pass

    def run(self) -> None:
        total = len(self.files)
        ok = skip = fail = 0
        started = time.time()

        with ThreadPoolExecutor(max_workers=min(self.concurrency, max(total, 1))) as pool:
            futures = [pool.submit(self._process_one, index, path) for index, path in enumerate(self.files)]
            for future in as_completed(futures):
                index, path, status, message = future.result()
                if status == "ok":
                    ok += 1
                    self.file_status.emit(index, "已完成")
                elif status == "skip":
                    skip += 1
                    self.file_status.emit(index, "跳过")
                elif status == "stopped":
                    self.file_status.emit(index, "未处理")
                else:
                    fail += 1
                    self.file_status.emit(index, "失败")
                self.progress.emit(index, path, status, message)
                self.count.emit(ok, skip, fail, total, Path(path).name)

        minutes, seconds = divmod(int(time.time() - started), 60)
        prefix = "已停止" if self.stop_flag.is_set() else "完成"
        self.finished_all.emit(f"{prefix}: 成功 {ok} 跳过 {skip} 失败 {fail} | 耗时 {minutes:02d}:{seconds:02d}")


class ASRPage(QWidget):
    request_download_dir = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("asr")
        self.config = load_app_config()
        self.toolchain = resolve_toolchain()
        self.worker: ASRWorkerThread | None = None
        self.row_index_map: list[int] = []
        self._build_ui()
        self._apply_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(TitleLabel("批量转文字", self))

        options = QHBoxLayout()
        options.addWidget(BodyLabel("ASR 接口:", self))
        self.engine_combo = ComboBox(self)
        self.engine_combo.addItems(list(ASR_ENGINE_OPTIONS))
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
        self.clear_btn = PushButton("清空列表", self)
        self.clear_btn.clicked.connect(self._clear_files)
        file_row.addWidget(self.add_files_btn)
        file_row.addWidget(self.add_folder_btn)
        file_row.addWidget(self.use_download_dir_btn)
        file_row.addWidget(self.clear_btn)
        file_row.addStretch(1)
        layout.addLayout(file_row)

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
        self.engine_combo.setCurrentText(self.config.asr_engine)
        self.format_combo.setCurrentText(self.config.asr_format)
        self.concurrency_combo.setCurrentText(str(self.config.asr_concurrency))
        self._refresh_out_label()

    def _save_state(self) -> None:
        self.config.asr_engine = self.engine_combo.currentText()
        self.config.asr_format = self.format_combo.currentText()
        self.config.asr_concurrency = int(self.concurrency_combo.currentText())
        save_app_config(self.config)

    def _refresh_out_label(self) -> None:
        text = self.config.asr_output_dir if self.config.asr_output_dir else "默认: 与源文件同目录"
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
        if not target and self.table.rowCount() > 0:
            item = self.table.item(0, 0)
            path = item.data(Qt.UserRole) if item else ""
            target = str(Path(path).parent) if path else ""
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
        self.table.setRowCount(0)

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
        if self.worker and self.worker.isRunning():
            self.stop()
            return
        pending = self._collect_unprocessed()
        if not pending:
            MessageBox("提示", "没有需要处理的文件。", self.window()).exec()
            return

        self._save_state()
        self.row_index_map = [row for row, _ in pending]
        files = [path for _, path in pending]
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
        self.start_btn.setText("停止")

    def stop(self) -> None:
        if self.worker:
            self.worker.stop()
            self.log.log("warn", "正在停止转文字任务...")

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
        window = self.window()
        if window:
            window.setWindowTitle(f"BBDown - 转文字 {done}/{total}")

    def _on_finished(self, summary: str) -> None:
        self.log.log("info", f"--- {summary} ---")
        self.start_btn.setText("开始转文字")
        window = self.window()
        if window:
            window.setWindowTitle(f"BBDown - {summary}")
        self.worker = None

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
        return bool(self.worker and self.worker.isRunning())
