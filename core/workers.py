from __future__ import annotations

import subprocess
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from .commands import build_download_command, build_login_command, shell_join
from .config import ENABLE_BBDOWN_DEBUG, MAX_LOG_LINE_LENGTH
from .media import MEDIA_EXTENSIONS
from .models import DownloadBatchResult, LoginResult, Toolchain


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
        self.thread_count = max(1, int(thread_count))
        self.toolchain = toolchain
        self.save_path = Path(save_dir)

    def batch_status_text(self, completed: int, total: int) -> str:
        return f"批量下载中 {completed}/{total} | 进行中 {self.active_count()} | 并发上限 {self.thread_count}"

    def _job_dir(self, index: int) -> Path:
        path = self.runtime_dir / "download_jobs" / f"{index:04d}_{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _unique_destination(self, target: Path) -> Path:
        if not target.exists():
            return target
        for counter in range(1, 1000):
            candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
            if not candidate.exists():
                return candidate
        return target.with_name(f"{target.stem} ({uuid.uuid4().hex[:8]}){target.suffix}")

    def _move_job_outputs(self, job_dir: Path) -> list[str]:
        moved: list[str] = []
        files = [
            path
            for path in sorted(job_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS and path.stat().st_size > 0
        ]
        for source in files:
            relative = source.relative_to(job_dir)
            destination = self._unique_destination(self.save_path / relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved.append(str(destination))
        return moved

    def run(self) -> None:
        failed_urls: list[str] = []
        no_output_urls: list[str] = []
        completed_urls: list[str] = []
        completed_files: list[str] = []
        total = len(self.urls)
        result_lock = threading.Lock()
        self.log.emit("info", f"批量任务开始，共 {total} 个链接，最多 {self.thread_count} 个同时运行。")
        self.status.emit(self.batch_status_text(0, total))

        def worker(index: int, url: str) -> tuple[int, str, int, list[str]]:
            if self.stop_flag.is_set():
                return index, url, 1, []
            self.log.emit("info", f"[{index}/{total}] 开始处理: {url}")
            job_dir = self._job_dir(index)
            try:
                command = build_download_command(url, str(job_dir), self.thread_count, self.toolchain)
                return_code = self.run_command_stream(command, prefix=f"[{index}/{total}] ")
                files = self._move_job_outputs(job_dir) if return_code == 0 else []
                return index, url, return_code, files
            finally:
                shutil.rmtree(job_dir, ignore_errors=True)

        with ThreadPoolExecutor(max_workers=min(self.thread_count, total)) as pool:
            futures = [pool.submit(worker, index, url) for index, url in enumerate(self.urls, start=1)]
            for future in as_completed(futures):
                if self.stop_flag.is_set():
                    break
                index, url, return_code, files = future.result()
                with result_lock:
                    if return_code == 0 and files:
                        completed_urls.append(url)
                        completed_files.extend(files)
                        for path in files:
                            self.log.emit("ok", f"[{index}/{total}] 输出文件: {path}")
                        self.log.emit("ok", f"[{index}/{total}] 任务完成。")
                    elif return_code == 0:
                        no_output_urls.append(url)
                        self.log.emit("warn", f"[{index}/{total}] 任务完成，但未产出音频文件。")
                    else:
                        failed_urls.append(url)
                        self.log.emit("fail", f"[{index}/{total}] 任务失败，退出码: {return_code}")
                    processed = len(completed_urls) + len(no_output_urls) + len(failed_urls)
                    self.status.emit(self.batch_status_text(processed, total))

        self.finished_all.emit(
            DownloadBatchResult(
                stopped=self.stop_flag.is_set(),
                failed_urls=failed_urls,
                no_output_urls=no_output_urls,
                completed_files=completed_files,
                completed=len(completed_urls),
                total=total,
            )
        )


class LoginWorkerThread(BaseProcessThread):
    finished_one = pyqtSignal(object)

    def __init__(self, mode: str, toolchain: Toolchain, runtime_dir: Path, log_encoding: str, parent=None) -> None:
        super().__init__(runtime_dir, log_encoding, parent)
        self.mode = mode
        self.toolchain = toolchain

    def run(self) -> None:
        command = build_login_command(self.mode, self.toolchain)
        return_code = self.run_command_stream(command)
        self.finished_one.emit(
            LoginResult(
                mode=self.mode,
                stopped=self.stop_flag.is_set(),
                return_code=return_code,
            )
        )
