from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from .config import MIN_CONCURRENCY
from .douyin_video_downloader import DouyinVideoDownloadResult, DouyinVideoDownloader
from .douyin_video_urls import DouyinVideoLink
from .models import DouyinVideoBatchResult
from .task_scheduler import run_limited_tasks


@dataclass(slots=True)
class _BatchState:
    completed_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)
    processed_ids: set[str] = field(default_factory=set)
    stopped_count: int = 0


class DouyinVideoWorkerThread(QThread):
    log = pyqtSignal(str, str)
    status = pyqtSignal(str)
    task_progress = pyqtSignal(str, int, int)
    task_status = pyqtSignal(str, str, str)
    batch_progress = pyqtSignal(int, int, int)
    finished_all = pyqtSignal(object)

    def __init__(
        self,
        links: list[DouyinVideoLink],
        save_dir: str,
        concurrency: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.links = links
        self.save_dir = Path(save_dir)
        self.concurrency = max(MIN_CONCURRENCY, int(concurrency))
        self.stop_event = threading.Event()
        self._counter_lock = threading.Lock()
        self._processed = 0
        self._active = 0
        self.downloader = DouyinVideoDownloader(self.stop_event, self.task_progress.emit)

    def stop(self) -> None:
        self.status.emit("正在停止任务，不再开始新任务...")
        self.downloader.stop()

    def run(self) -> None:
        try:
            result = self._run_batch()
        except Exception as exc:
            self.log.emit("fail", f"批量下载异常: {exc}")
            stopped = self.stop_event.is_set()
            result = DouyinVideoBatchResult(
                stopped=stopped,
                total=len(self.links),
                failed=0 if stopped else len(self.links),
                stopped_count=len(self.links) if stopped else 0,
                failed_urls=[] if stopped else [link.url for link in self.links],
            )
        self.finished_all.emit(result)

    def _run_batch(self) -> DouyinVideoBatchResult:
        total = len(self.links)
        state = _BatchState()

        self.log.emit("info", f"开始下载，共 {total} 个视频，并发 {self.concurrency}。")
        self._emit_batch_progress(total)

        for result in run_limited_tasks(
            self.links,
            max_workers=min(self.concurrency, max(total, 1)),
            submit_one=lambda index, link: self._download_one(total, index, link),
            should_stop=self.stop_event.is_set,
            on_error=self._task_error,
            start_index=1,
        ):
            self._record_result(result, state)
            self._emit_batch_progress(total)

        self._mark_unstarted(state)

        return DouyinVideoBatchResult(
            stopped=self.stop_event.is_set(),
            total=total,
            completed=len(state.completed_files),
            skipped=len(state.skipped_files),
            failed=len(state.failed_urls),
            stopped_count=state.stopped_count,
            completed_files=state.completed_files,
            skipped_files=state.skipped_files,
            failed_urls=state.failed_urls,
        )

    def _download_one(
        self,
        total: int,
        _index: int,
        link: DouyinVideoLink,
    ) -> DouyinVideoDownloadResult:
        if self.stop_event.is_set():
            return DouyinVideoDownloadResult(link=link, status="stopped", message="已停止")
        with self._counter_lock:
            self._active += 1
        self.task_status.emit(link.video_id, "下载中", "")
        self._emit_batch_progress(total)
        try:
            return self.downloader.download(link, self.save_dir)
        finally:
            with self._counter_lock:
                self._active = max(0, self._active - 1)
            self._emit_batch_progress(total)

    def _task_error(
        self,
        _index: int,
        link: DouyinVideoLink,
        exc: Exception,
    ) -> DouyinVideoDownloadResult:
        self.log.emit("fail", f"{link.video_id}: 下载任务异常: {exc}")
        return DouyinVideoDownloadResult(link=link, status="failed", message="下载任务异常")

    def _record_result(self, result: DouyinVideoDownloadResult, state: _BatchState) -> None:
        state.processed_ids.add(result.link.video_id)
        with self._counter_lock:
            self._processed += 1

        output_name = Path(result.output_path).name
        if result.status == "completed":
            state.completed_files.append(result.output_path)
            self.task_status.emit(result.link.video_id, "已完成", output_name)
            self.log.emit("ok", output_name)
        elif result.status == "exists":
            state.skipped_files.append(result.output_path)
            self.task_status.emit(result.link.video_id, "已存在", output_name)
            self.log.emit("skip", f"{output_name} 已存在")
        elif result.status == "failed":
            state.failed_urls.append(result.link.url)
            self.task_status.emit(result.link.video_id, "失败", result.message)
            self.log.emit("fail", f"{result.link.video_id}: {result.message}")
        else:
            state.stopped_count += 1
            self.task_status.emit(result.link.video_id, "已停止", "")

    def _mark_unstarted(self, state: _BatchState) -> None:
        if not self.stop_event.is_set():
            return
        for link in self.links:
            if link.video_id in state.processed_ids:
                continue
            state.stopped_count += 1
            self.task_status.emit(link.video_id, "已停止", "")

    def _emit_batch_progress(self, total: int) -> None:
        with self._counter_lock:
            processed = self._processed
            active = self._active
        self.batch_progress.emit(processed, total, active)
        if self.stop_event.is_set():
            self.status.emit(f"正在停止 | 已处理 {processed}/{total} | 进行中 {active}")
        else:
            self.status.emit(f"下载中 {processed}/{total} | 进行中 {active} | 并发 {self.concurrency}")
