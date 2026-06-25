from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.asr_task import ASRTaskResult, process_url_asr_task
from core.config import MIN_CONCURRENCY
from core.task_scheduler import run_limited_tasks
from core.url_audio import audio_name_from_url


@dataclass(slots=True)
class UrlASRBatchResult:
    summary: str
    output_dir: str
    stopped: bool = False
    failed_urls: list[str] = field(default_factory=list)
    ok: int = 0
    skip: int = 0
    fail: int = 0
    total: int = 0


def default_url_output_dir() -> Path:
    return Path.home() / "Downloads" / "BBDownTranscripts"


class UrlASRWorkerThread(QThread):
    progress = pyqtSignal(int, str, str, str)
    count = pyqtSignal(int, int, int, int, str)
    finished_all = pyqtSignal(object)

    def __init__(
        self,
        urls: list[str],
        engine_name: str,
        export_format: str,
        concurrency: int,
        out_dir: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.urls = urls
        self.engine_name = engine_name
        self.export_format = export_format.lower()
        self.concurrency = max(MIN_CONCURRENCY, int(concurrency))
        self.out_dir = Path(out_dir) if out_dir else default_url_output_dir()
        self.stop_flag = threading.Event()

    def stop(self) -> None:
        self.stop_flag.set()

    def _process_one(self, index: int, url: str) -> ASRTaskResult:
        return process_url_asr_task(
            index=index,
            url=url,
            engine_name=self.engine_name,
            export_format=self.export_format,
            out_dir=self.out_dir,
            stopped=self.stop_flag.is_set,
        )

    def run(self) -> None:
        total = len(self.urls)
        ok = skip = fail = 0
        failed_urls: list[str] = []
        processed_indices: set[int] = set()
        started = time.time()

        for result in run_limited_tasks(
            self.urls,
            max_workers=min(self.concurrency, max(total, 1)),
            submit_one=self._process_one,
            should_stop=self.stop_flag.is_set,
        ):
            processed_indices.add(result.index)
            name = audio_name_from_url(result.source, result.index)
            if result.status == "ok":
                ok += 1
            elif result.status == "skip":
                skip += 1
            elif result.status == "stopped":
                failed_urls.append(result.source)
            else:
                fail += 1
                failed_urls.append(result.source)
            self.progress.emit(result.index, result.source, result.status, result.message)
            self.count.emit(ok, skip, fail, total, name)

        if self.stop_flag.is_set():
            for index, url in enumerate(self.urls):
                if index not in processed_indices:
                    failed_urls.append(url)

        minutes, seconds = divmod(int(time.time() - started), 60)
        stopped = self.stop_flag.is_set()
        prefix = "已停止" if stopped else "完成"
        summary = f"{prefix}: 成功 {ok} 跳过 {skip} 失败 {fail} | 耗时 {minutes:02d}:{seconds:02d}"
        self.finished_all.emit(
            UrlASRBatchResult(
                summary=summary,
                output_dir=str(self.out_dir),
                stopped=stopped,
                failed_urls=failed_urls,
                ok=ok,
                skip=skip,
                fail=fail,
                total=total,
            )
        )
