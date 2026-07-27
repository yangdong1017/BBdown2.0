from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import requests


TOS_PUBLIC_BASE_URL = "https://bbdown.tos-cn-beijing.volces.com"
TOS_TEMP_PREFIX = "asr-temp"
TOS_TIMEOUT = (10, 120)
TOS_MAX_ATTEMPTS = 3
TOS_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
TOS_UPLOAD_SUCCESS_STATUS = {200, 201, 204}
TOS_DELETE_SUCCESS_STATUS = {200, 202, 204, 404}


class TOSStorageError(RuntimeError):
    pass


class _UploadStopped(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PublicTOSObject:
    key: str
    url: str


class PublicTOSStorage:
    """Anonymous temporary object storage used by local-file Doubao ASR."""

    def __init__(
        self,
        *,
        base_url: str = TOS_PUBLIC_BASE_URL,
        prefix: str = TOS_TEMP_PREFIX,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix.strip("/")

    def upload(
        self,
        path: str | Path,
        *,
        suffix: str,
        content_type: str,
        stopped: Callable[[], bool],
    ) -> PublicTOSObject:
        source = Path(path)
        if not source.is_file() or source.stat().st_size <= 0:
            raise TOSStorageError("临时音频不存在或内容为空。")

        normalized_suffix = suffix.lower()
        if not normalized_suffix.startswith("."):
            normalized_suffix = f".{normalized_suffix}"
        key = f"{self.prefix}/{uuid.uuid4().hex}{normalized_suffix}"
        temporary_object = PublicTOSObject(key=key, url=f"{self.base_url}/{key}")
        last_status = 0
        attempted_upload = False

        for attempt in range(TOS_MAX_ATTEMPTS):
            try:
                _check_stopped(stopped)
            except TOSStorageError:
                if attempted_upload:
                    self.delete(temporary_object)
                raise
            try:
                with source.open("rb") as handle:
                    body = _StopAwareUpload(handle, stopped)
                    attempted_upload = True
                    response = requests.put(
                        temporary_object.url,
                        data=body,
                        headers={
                            "Content-Type": content_type,
                            "Content-Length": str(source.stat().st_size),
                        },
                        timeout=TOS_TIMEOUT,
                    )
                last_status = response.status_code
                _close_response(response)
                if last_status in TOS_UPLOAD_SUCCESS_STATUS:
                    return temporary_object
                retryable = last_status in TOS_RETRYABLE_STATUS
            except _UploadStopped as exc:
                self.delete(temporary_object)
                raise TOSStorageError("已停止") from exc
            except requests.RequestException as exc:
                if stopped():
                    self.delete(temporary_object)
                    raise TOSStorageError("已停止") from exc
                retryable = True
            except OSError as exc:
                self.delete(temporary_object)
                raise TOSStorageError("无法读取待上传的临时音频。") from exc

            if not retryable or attempt >= TOS_MAX_ATTEMPTS - 1:
                break
            try:
                _wait_or_stop(2**attempt, stopped)
            except TOSStorageError:
                self.delete(temporary_object)
                raise

        self.delete(temporary_object)
        if last_status in {401, 403}:
            raise TOSStorageError("临时音频上传失败，存储服务暂不可用。")
        raise TOSStorageError("临时音频上传失败，请检查网络后重试。")

    def delete(self, temporary_object: PublicTOSObject | str) -> bool:
        url = temporary_object.url if isinstance(temporary_object, PublicTOSObject) else temporary_object
        for attempt in range(TOS_MAX_ATTEMPTS):
            try:
                response = requests.delete(url, timeout=(TOS_TIMEOUT[0], 30))
                status = response.status_code
                _close_response(response)
                if status in TOS_DELETE_SUCCESS_STATUS:
                    return True
                retryable = status in TOS_RETRYABLE_STATUS
            except requests.RequestException:
                retryable = True

            if not retryable or attempt >= TOS_MAX_ATTEMPTS - 1:
                break
            time.sleep(2**attempt)
        return False


class _StopAwareUpload:
    def __init__(self, handle: BinaryIO, stopped: Callable[[], bool]) -> None:
        self.handle = handle
        self.stopped = stopped

    def read(self, size: int = -1) -> bytes:
        if self.stopped():
            raise _UploadStopped("已停止")
        data = self.handle.read(size)
        if self.stopped():
            raise _UploadStopped("已停止")
        return data


def _check_stopped(stopped: Callable[[], bool]) -> None:
    if stopped():
        raise TOSStorageError("已停止")


def _wait_or_stop(seconds: float, stopped: Callable[[], bool]) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        _check_stopped(stopped)
        time.sleep(min(0.1, deadline - time.monotonic()))
    _check_stopped(stopped)


def _close_response(response: requests.Response) -> None:
    try:
        response.close()
    except Exception:
        pass
