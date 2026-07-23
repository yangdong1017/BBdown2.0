from __future__ import annotations

import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from .commands import build_download_command, build_login_command, shell_join
from .config import ENABLE_BBDOWN_DEBUG, MAX_LOG_LINE_LENGTH, MIN_CONCURRENCY
from .media import MEDIA_EXTENSIONS
from .models import DownloadBatchResult, LoginResult, Toolchain
from .output_paths import OutputPathAllocator
from .task_scheduler import run_limited_tasks


@dataclass(slots=True)
class _DownloadBatchState:
    failed_urls: list[str] = field(default_factory=list)
    no_output_urls: list[str] = field(default_factory=list)
    completed_files: list[str] = field(default_factory=list)
    processed_indices: set[int] = field(default_factory=set)
    completed: int = 0


class BaseProcessThread(QThread):
    log = pyqtSignal(str, str)
    status = pyqtSignal(str)

    def __init__(self, runtime_dir: Path, log_encoding: str, parent=None) -> None:
        super().__init__(parent)
        self.runtime_dir = runtime_dir
        self.log_encoding = log_encoding
        self.stop_flag = threading.Event()
        self._processes: dict[int, subprocess.Popen[str]] = {}
        self._process_lock = threading.Lock()

    def stop(self) -> None:
        self.stop_flag.set()
        for process in self.list_processes():
            self.kill_process_tree(process)

    def register_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            self._processes[process.pid] = process

    def unregister_process(self, process: subprocess.Popen[str]) -> None:
        with self._process_lock:
            self._processes.pop(process.pid, None)

    def list_processes(self) -> list[subprocess.Popen[str]]:
        with self._process_lock:
            return list(self._processes.values())

    def active_count(self) -> int:
        return len(self.list_processes())

    def kill_process_tree(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            self.unregister_process(process)
            return

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=creationflags,
            )
        except Exception:
            try:
                process.kill()
            except OSError:
                pass
        finally:
            self.unregister_process(process)

    def launch_process(self, command: list[str]) -> subprocess.Popen[str]:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            command,
            cwd=str(self.runtime_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=self.log_encoding,
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )

    def looks_like_qr_console_art(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < 40:
            return False
        normal_chars = sum(ch.isalnum() or ch.isspace() or ch in "[]-:./_\\()" for ch in stripped)
        return normal_chars / len(stripped) < 0.25

    def format_log_line(self, line: str) -> str | None:
        if not ENABLE_BBDOWN_DEBUG and line.startswith(("Accept-Encoding:", "Cache-Control:", "Cookie:", "Referer:")):
            return None
        if line.lstrip().startswith("[#"):
            return None
        if " - Response: {" in line and len(line) > MAX_LOG_LINE_LENGTH:
            return line[:MAX_LOG_LINE_LENGTH] + " ... [已截断]"
        if len(line) > MAX_LOG_LINE_LENGTH:
            return line[:MAX_LOG_LINE_LENGTH] + " ... [已截断]"
        return line

    def run_command_stream(self, command: list[str], prefix: str = "") -> int:
        self.log.emit("info", f"{prefix}启动命令: {shell_join(command)}")
        self.log.emit("info", f"{prefix}运行目录: {self.runtime_dir}")
        try:
            process = self.launch_process(command)
        except Exception as exc:
            self.log.emit("fail", f"{prefix}启动失败: {exc}")
            return 1

        self.register_process(process)
        try:
            if process.stdout is not None:
                for raw_line in process.stdout:
                    line = raw_line.replace("\r", "").rstrip("\n")
                    if not line:
                        continue
                    if self.looks_like_qr_console_art(line):
                        continue
                    formatted = self.format_log_line(line)
                    if formatted is not None:
                        self.log.emit("info", f"{prefix}{formatted}")
            return process.wait()
        finally:
            self.unregister_process(process)


class DownloadWorkerThread(BaseProcessThread):
    finished_all = pyqtSignal(object)
    progress = pyqtSignal(int, int, int)

    def __init__(
        self,
        urls: list[str],
        save_dir: str,
        thread_count: int,
        toolchain: Toolchain,
        runtime_dir: Path,
        log_encoding: str,
        parent=None,
    ) -> None:
        super().__init__(runtime_dir, log_encoding, parent)
        self.urls = urls
        self.save_dir = save_dir
        self.thread_count = max(MIN_CONCURRENCY, int(thread_count))
        self.toolchain = toolchain
        self.save_path = Path(save_dir)
        self.output_paths = OutputPathAllocator()
        self._progress_lock = threading.Lock()
        self._processed = 0
        self._active_jobs = 0

    def batch_status_text(self, completed: int, total: int) -> str:
        return f"批量下载中 {completed}/{total} | 进行中 {self.active_count()} | 并发上限 {self.thread_count}"

    def _job_dir(self, index: int) -> Path:
        path = self.runtime_dir / "download_jobs" / f"{index:04d}_{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _move_job_outputs(self, job_dir: Path) -> list[str]:
        moved: list[str] = []
        files = [
            path
            for path in sorted(job_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS and path.stat().st_size > 0
        ]
        for source in files:
            relative = source.relative_to(job_dir)
            destination = self.output_paths.reserve(self.save_path / relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append(str(destination))
        return moved

    def run(self) -> None:
        try:
            result = self._run_batch()
        except Exception as exc:
            self.log.emit("fail", f"批量任务异常: {exc}")
            result = DownloadBatchResult(
                stopped=self.stop_flag.is_set(),
                failed_urls=list(self.urls),
                completed=0,
                total=len(self.urls),
            )
        self.finished_all.emit(result)

    def _run_batch(self) -> DownloadBatchResult:
        total = len(self.urls)
        state = _DownloadBatchState()

        self.log.emit("info", f"批量任务开始，共 {total} 个链接，最多 {self.thread_count} 个同时运行。")
        self._emit_download_progress(total)

        for result in run_limited_tasks(
            self.urls,
            max_workers=min(self.thread_count, max(total, 1)),
            submit_one=lambda index, url: self._download_one(total, index, url),
            should_stop=self.stop_flag.is_set,
            on_error=lambda index, url, exc: self._download_error(total, index, url, exc),
            start_index=1,
        ):
            self._record_download_result(total, result, state)

        self._mark_unstarted_downloads(state)

        return DownloadBatchResult(
            stopped=self.stop_flag.is_set(),
            failed_urls=state.failed_urls,
            no_output_urls=state.no_output_urls,
            completed_files=state.completed_files,
            completed=state.completed,
            total=total,
        )

    def _download_one(self, total: int, index: int, url: str) -> tuple[int, str, int, list[str]]:
        if self.stop_flag.is_set():
            return index, url, 1, []
        self.log.emit("info", f"[{index}/{total}] 开始处理: {url}")
        self._change_active_jobs(1, total)
        job_dir = self._job_dir(index)
        try:
            command = build_download_command(url, str(job_dir), self.thread_count, self.toolchain)
            return_code = self.run_command_stream(command, prefix=f"[{index}/{total}] ")
            files = self._move_job_outputs(job_dir) if return_code == 0 else []
            return index, url, return_code, files
        finally:
            self._change_active_jobs(-1, total)
            shutil.rmtree(job_dir, ignore_errors=True)

    def _download_error(
        self,
        total: int,
        index: int,
        url: str,
        exc: Exception,
    ) -> tuple[int, str, int, list[str]]:
        self.log.emit("fail", f"[{index}/{total}] 任务异常: {exc}")
        return index, url, 1, []

    def _record_download_result(
        self,
        total: int,
        result: tuple[int, str, int, list[str]],
        state: _DownloadBatchState,
    ) -> None:
        index, url, return_code, files = result
        state.processed_indices.add(index)
        with self._progress_lock:
            self._processed += 1
        if return_code == 0 and files:
            state.completed += 1
            state.completed_files.extend(files)
            for path in files:
                self.log.emit("ok", f"[{index}/{total}] 输出文件: {path}")
            self.log.emit("ok", f"[{index}/{total}] 任务完成。")
        elif return_code == 0:
            state.no_output_urls.append(url)
            self.log.emit("warn", f"[{index}/{total}] 任务完成，但未产出音频文件。")
        else:
            state.failed_urls.append(url)
            self.log.emit("fail", f"[{index}/{total}] 任务失败，退出码: {return_code}")
        self._emit_download_progress(total)

    def _mark_unstarted_downloads(self, state: _DownloadBatchState) -> None:
        if not self.stop_flag.is_set():
            return
        for index, url in enumerate(self.urls, start=1):
            if index not in state.processed_indices:
                state.failed_urls.append(url)

    def _change_active_jobs(self, delta: int, total: int) -> None:
        with self._progress_lock:
            self._active_jobs = max(0, self._active_jobs + delta)
        self._emit_download_progress(total)

    def _emit_download_progress(self, total: int) -> None:
        with self._progress_lock:
            processed = self._processed
            active_jobs = self._active_jobs
        self.progress.emit(processed, total, active_jobs)
        self.status.emit(
            f"批量下载中 {processed}/{total} | 进行中 {active_jobs} | 并发上限 {self.thread_count}"
        )


class LoginWorkerThread(BaseProcessThread):
    finished_one = pyqtSignal(object)

    def __init__(self, mode: str, toolchain: Toolchain, runtime_dir: Path, log_encoding: str, parent=None) -> None:
        super().__init__(runtime_dir, log_encoding, parent)
        self.mode = mode
        self.toolchain = toolchain

    def run(self) -> None:
        return_code = 1
        try:
            command = build_login_command(self.mode, self.toolchain)
            return_code = self.run_command_stream(command)
        except Exception as exc:
            self.log.emit("fail", f"登录任务异常: {exc}")
        self.finished_one.emit(
            LoginResult(
                mode=self.mode,
                stopped=self.stop_flag.is_set(),
                return_code=return_code,
            )
        )
