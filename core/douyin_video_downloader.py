from __future__ import annotations

import errno
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .config import DOUYIN_VIDEO_CHUNK_SIZE, DOUYIN_VIDEO_RETRY_COUNT, DOUYIN_VIDEO_TIMEOUT
from .douyin_media import DouyinMediaLink
from .errors import UserFacingError


MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "video/mp4,audio/mpeg,audio/*;q=0.9,video/*;q=0.8,*/*;q=0.7",
}

ProgressCallback = Callable[[str, int, int], None]

# One connection pool per batch. Without it every task and every retry opened a
# brand new connection, so the pool never got reused under high concurrency.
DEFAULT_CONNECTION_POOL_SIZE = 10


@dataclass(slots=True)
class DouyinMediaDownloadResult:
    link: DouyinMediaLink
    status: str
    output_path: str = ""
    message: str = ""


class MediaDownloadError(UserFacingError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class DouyinMediaDownloader:
    def __init__(
        self,
        stop_event: threading.Event,
        progress_callback: ProgressCallback,
        *,
        pool_size: int = DEFAULT_CONNECTION_POOL_SIZE,
    ) -> None:
        self.stop_event = stop_event
        self.progress_callback = progress_callback
        self._responses: dict[str, requests.Response] = {}
        self._response_lock = threading.Lock()
        self._pool_size = max(1, int(pool_size))
        self._session: requests.Session | None = None
        self._session_lock = threading.Lock()

    def stop(self) -> None:
        self.stop_event.set()
        with self._response_lock:
            responses = list(self._responses.values())
        for response in responses:
            try:
                response.close()
            except Exception:
                pass
        self.close()

    def close(self) -> None:
        """Release the shared connection pool once a batch is over."""
        with self._session_lock:
            session, self._session = self._session, None
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    def _session_for_download(self) -> requests.Session:
        with self._session_lock:
            if self._session is None:
                session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=self._pool_size,
                    pool_maxsize=self._pool_size,
                    max_retries=0,
                )
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                self._session = session
            return self._session

    def download(self, link: DouyinMediaLink, save_dir: Path) -> DouyinMediaDownloadResult:
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            target = save_dir / f"{link.task_id}{link.file_suffix}"
            partial = save_dir / f"{link.task_id}{link.file_suffix}.part"
            if target.exists() and target.stat().st_size > 0:
                return DouyinMediaDownloadResult(link=link, status="exists", output_path=str(target))
        except OSError as exc:
            return DouyinMediaDownloadResult(
                link=link,
                status="failed",
                message=_file_error_message(exc, link.media_label),
            )

        last_message = "下载失败"
        for attempt in range(1, DOUYIN_VIDEO_RETRY_COUNT + 1):
            if self.stop_event.is_set():
                return self._stopped_result(link, partial)

            partial.unlink(missing_ok=True)
            try:
                return self._download_once(link, target, partial)
            except MediaDownloadError as exc:
                last_message = str(exc)
                retryable = exc.retryable
            except requests.RequestException as exc:
                last_message = _request_error_message(exc, link.media_label)
                retryable = not isinstance(exc, requests.TooManyRedirects)
            except OSError as exc:
                last_message = _file_error_message(exc, link.media_label)
                retryable = False
            except Exception:
                last_message = "下载失败"
                retryable = False

            partial.unlink(missing_ok=True)
            if self.stop_event.is_set() or last_message == "已停止":
                return self._stopped_result(link, partial)
            if not retryable or attempt >= DOUYIN_VIDEO_RETRY_COUNT:
                break
            if self.stop_event.wait(2 ** (attempt - 1)):
                return self._stopped_result(link, partial)

        return DouyinMediaDownloadResult(link=link, status="failed", message=last_message)

    def _download_once(
        self,
        link: DouyinMediaLink,
        target: Path,
        partial: Path,
    ) -> DouyinMediaDownloadResult:
        response: requests.Response | None = None
        try:
            response = self._session_for_download().get(
                link.url,
                headers=MEDIA_HEADERS,
                stream=True,
                allow_redirects=True,
                timeout=DOUYIN_VIDEO_TIMEOUT,
            )
            self._register_response(link.task_id, response)
            self._check_response(response, link)
            downloaded, total_bytes = self._stream_to_partial(link.task_id, response, partial)
            self._validate_download(downloaded, total_bytes, link.media_label)
            os.replace(partial, target)
            self.progress_callback(link.task_id, downloaded, total_bytes or downloaded)
            return DouyinMediaDownloadResult(link=link, status="completed", output_path=str(target))
        finally:
            if response is not None:
                self._unregister_response(link.task_id, response)
                response.close()

    def _stream_to_partial(
        self,
        task_id: str,
        response: requests.Response,
        partial: Path,
    ) -> tuple[int, int]:
        total_bytes = _content_length(response)
        downloaded = 0
        last_emit_at = 0.0
        self.progress_callback(task_id, 0, total_bytes)

        with partial.open("wb") as output:
            for chunk in response.iter_content(chunk_size=DOUYIN_VIDEO_CHUNK_SIZE):
                if self.stop_event.is_set():
                    raise MediaDownloadError("已停止", retryable=False)
                if not chunk:
                    continue
                output.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_emit_at >= 0.25:
                    self.progress_callback(task_id, downloaded, total_bytes)
                    last_emit_at = now
        return downloaded, total_bytes

    def _validate_download(self, downloaded: int, total_bytes: int, media_label: str) -> None:
        if self.stop_event.is_set():
            raise MediaDownloadError("已停止", retryable=False)
        if downloaded <= 0:
            raise MediaDownloadError(f"没有收到{media_label}数据", retryable=True)
        if total_bytes and downloaded < total_bytes:
            raise MediaDownloadError(f"{media_label}下载不完整", retryable=True)

    @staticmethod
    def _stopped_result(link: DouyinMediaLink, partial: Path) -> DouyinMediaDownloadResult:
        partial.unlink(missing_ok=True)
        return DouyinMediaDownloadResult(link=link, status="stopped", message="已停止")

    def _register_response(self, task_id: str, response: requests.Response) -> None:
        with self._response_lock:
            self._responses[task_id] = response

    def _unregister_response(self, task_id: str, response: requests.Response) -> None:
        with self._response_lock:
            if self._responses.get(task_id) is response:
                self._responses.pop(task_id, None)

    @staticmethod
    def _check_response(response: requests.Response, link: DouyinMediaLink) -> None:
        status = response.status_code
        if status in {403, 404}:
            raise MediaDownloadError(f"{link.media_label}链接已失效", retryable=False)
        if status == 429:
            raise MediaDownloadError("请求过于频繁", retryable=True)
        if status >= 500:
            raise MediaDownloadError(f"{link.media_label}服务器暂时不可用", retryable=True)
        if status != 200:
            raise MediaDownloadError(f"下载请求失败（HTTP {status}）", retryable=status in {408, 425})

        media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if not media_type.startswith(link.content_prefix):
            raise MediaDownloadError(f"该链接没有返回{link.media_label}", retryable=False)


def _content_length(response: requests.Response) -> int:
    try:
        return max(0, int(response.headers.get("Content-Length", "0")))
    except (TypeError, ValueError):
        return 0


def _request_error_message(exc: requests.RequestException, media_label: str) -> str:
    if isinstance(exc, requests.Timeout):
        return "网络连接超时"
    if isinstance(exc, requests.TooManyRedirects):
        return f"{media_label}跳转地址异常"
    if isinstance(exc, requests.ConnectionError):
        return "网络连接失败"
    return "下载请求失败"


def _file_error_message(exc: OSError, media_label: str) -> str:
    if isinstance(exc, PermissionError):
        return "保存目录不可用"
    if exc.errno == errno.ENOSPC:
        return "磁盘空间不足"
    return f"保存{media_label}失败"
