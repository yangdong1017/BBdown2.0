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
from .douyin_video_urls import DouyinVideoLink


VIDEO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
}

ProgressCallback = Callable[[str, int, int], None]


@dataclass(slots=True)
class DouyinVideoDownloadResult:
    link: DouyinVideoLink
    status: str
    output_path: str = ""
    message: str = ""


class VideoDownloadError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class DouyinVideoDownloader:
    def __init__(self, stop_event: threading.Event, progress_callback: ProgressCallback) -> None:
        self.stop_event = stop_event
        self.progress_callback = progress_callback
        self._responses: dict[str, requests.Response] = {}
        self._response_lock = threading.Lock()

    def stop(self) -> None:
        self.stop_event.set()
        with self._response_lock:
            responses = list(self._responses.values())
        for response in responses:
            try:
                response.close()
            except Exception:
                pass

    def download(self, link: DouyinVideoLink, save_dir: Path) -> DouyinVideoDownloadResult:
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            target = save_dir / f"{link.video_id}.mp4"
            partial = save_dir / f"{link.video_id}.mp4.part"
            if target.exists() and target.stat().st_size > 0:
                return DouyinVideoDownloadResult(link=link, status="exists", output_path=str(target))
        except OSError as exc:
            return DouyinVideoDownloadResult(link=link, status="failed", message=_file_error_message(exc))

        last_message = "下载失败"
        for attempt in range(1, DOUYIN_VIDEO_RETRY_COUNT + 1):
            if self.stop_event.is_set():
                return self._stopped_result(link, partial)

            partial.unlink(missing_ok=True)
            try:
                return self._download_once(link, target, partial)
            except VideoDownloadError as exc:
                last_message = str(exc)
                retryable = exc.retryable
            except requests.RequestException as exc:
                last_message = _request_error_message(exc)
                retryable = not isinstance(exc, requests.TooManyRedirects)
            except OSError as exc:
                last_message = _file_error_message(exc)
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

        return DouyinVideoDownloadResult(link=link, status="failed", message=last_message)

    def _download_once(
        self,
        link: DouyinVideoLink,
        target: Path,
        partial: Path,
    ) -> DouyinVideoDownloadResult:
        response: requests.Response | None = None
        try:
            with requests.Session() as session:
                response = session.get(
                    link.url,
                    headers=VIDEO_HEADERS,
                    stream=True,
                    allow_redirects=True,
                    timeout=DOUYIN_VIDEO_TIMEOUT,
                )
                self._register_response(link.video_id, response)
                self._check_response(response)
                downloaded, total_bytes = self._stream_to_partial(link.video_id, response, partial)
                self._validate_download(downloaded, total_bytes)
                os.replace(partial, target)
                self.progress_callback(link.video_id, downloaded, total_bytes or downloaded)
                return DouyinVideoDownloadResult(link=link, status="completed", output_path=str(target))
        finally:
            if response is not None:
                self._unregister_response(link.video_id, response)
                response.close()

    def _stream_to_partial(
        self,
        video_id: str,
        response: requests.Response,
        partial: Path,
    ) -> tuple[int, int]:
        total_bytes = _content_length(response)
        downloaded = 0
        last_emit_at = 0.0
        self.progress_callback(video_id, 0, total_bytes)

        with partial.open("wb") as output:
            for chunk in response.iter_content(chunk_size=DOUYIN_VIDEO_CHUNK_SIZE):
                if self.stop_event.is_set():
                    raise VideoDownloadError("已停止", retryable=False)
                if not chunk:
                    continue
                output.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_emit_at >= 0.25:
                    self.progress_callback(video_id, downloaded, total_bytes)
                    last_emit_at = now
        return downloaded, total_bytes

    def _validate_download(self, downloaded: int, total_bytes: int) -> None:
        if self.stop_event.is_set():
            raise VideoDownloadError("已停止", retryable=False)
        if downloaded <= 0:
            raise VideoDownloadError("没有收到视频数据", retryable=True)
        if total_bytes and downloaded < total_bytes:
            raise VideoDownloadError("视频下载不完整", retryable=True)

    @staticmethod
    def _stopped_result(link: DouyinVideoLink, partial: Path) -> DouyinVideoDownloadResult:
        partial.unlink(missing_ok=True)
        return DouyinVideoDownloadResult(link=link, status="stopped", message="已停止")

    def _register_response(self, video_id: str, response: requests.Response) -> None:
        with self._response_lock:
            self._responses[video_id] = response

    def _unregister_response(self, video_id: str, response: requests.Response) -> None:
        with self._response_lock:
            if self._responses.get(video_id) is response:
                self._responses.pop(video_id, None)

    @staticmethod
    def _check_response(response: requests.Response) -> None:
        status = response.status_code
        if status in {403, 404}:
            raise VideoDownloadError("视频链接已失效", retryable=False)
        if status == 429:
            raise VideoDownloadError("请求过于频繁", retryable=True)
        if status >= 500:
            raise VideoDownloadError("视频服务器暂时不可用", retryable=True)
        if status != 200:
            raise VideoDownloadError(f"下载请求失败（HTTP {status}）", retryable=status in {408, 425})

        media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if not media_type.startswith("video/"):
            raise VideoDownloadError("该链接没有返回视频", retryable=False)


def _content_length(response: requests.Response) -> int:
    try:
        return max(0, int(response.headers.get("Content-Length", "0")))
    except (TypeError, ValueError):
        return 0


def _request_error_message(exc: requests.RequestException) -> str:
    if isinstance(exc, requests.Timeout):
        return "网络连接超时"
    if isinstance(exc, requests.TooManyRedirects):
        return "视频跳转地址异常"
    if isinstance(exc, requests.ConnectionError):
        return "网络连接失败"
    return "下载请求失败"


def _file_error_message(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "保存目录不可用"
    if exc.errno == errno.ENOSPC:
        return "磁盘空间不足"
    return "保存视频失败"
