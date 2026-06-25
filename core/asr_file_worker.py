from __future__ import annotations

import threading
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.asr_task import ASRTaskResult, process_file_asr_task
from core.config import MIN_CONCURRENCY
from core.task_scheduler import run_limited_tasks


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
        self.concurrency = max(MIN_CONCURRENCY, int(concurrency))
        self.out_dir = out_dir
        self.ffmpeg_path = ffmpeg_path
        self.stop_flag = threading.Event()

    def stop(self) -> None:
        self.stop_flag.set()

    def _process_one(self, index: int, path: str) -> ASRTaskResult:
        if self.stop_flag.is_set():
            return ASRTaskResult(index, path, "stopped", "已停止")

        self.file_status.emit(index, "处理中")
        return process_file_asr_task(
            index=index,
            path=path,
            engine_name=self.engine_name,
            export_format=self.export_format,
            out_dir=self.out_dir,
            ffmpeg_path=self.ffmpeg_path,
            stopped=self.stop_flag.is_set,
        )

    def run(self) -> None:
        total = len(self.files)
        ok = skip = fail = 0
        processed_indices: set[int] = set()
        started = time.time()

        for result in run_limited_tasks(
            self.files,
            max_workers=min(self.concurrency, max(total, 1)),
            submit_one=self._process_one,
            should_stop=self.stop_flag.is_set,
        ):
            processed_indices.add(result.index)
            if result.status == "ok":
                ok += 1
                self.file_status.emit(result.index, "已完成")
            elif result.status == "skip":
                skip += 1
                self.file_status.emit(result.index, "跳过")
            elif result.status == "stopped":
                self.file_status.emit(result.index, "未处理")
            else:
                fail += 1
                self.file_status.emit(result.index, "失败")
            self.progress.emit(result.index, result.source, result.status, result.message)
            self.count.emit(ok, skip, fail, total, Path(result.source).name)

        if self.stop_flag.is_set():
            for index in range(total):
                if index not in processed_indices:
                    self.file_status.emit(index, "未处理")

        minutes, seconds = divmod(int(time.time() - started), 60)
        prefix = "已停止" if self.stop_flag.is_set() else "完成"
        self.finished_all.emit(f"{prefix}: 成功 {ok} 跳过 {skip} 失败 {fail} | 耗时 {minutes:02d}:{seconds:02d}")
