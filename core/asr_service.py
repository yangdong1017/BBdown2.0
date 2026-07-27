from __future__ import annotations

import errno
import logging
from collections.abc import Callable
from pathlib import Path

import requests

from bk_asr import BcutASR
from core.config import BCUT_ENGINE_NAME
from core.errors import UserFacingError


ENGINE_MAP = {
    BCUT_ENGINE_NAME: BcutASR,
}

STOPPED_MESSAGE = "已停止"
GENERIC_MESSAGE = "处理失败，请重试。"
NOT_READY_MESSAGE = "识别服务结果暂未就绪，已多次重试后仍失败。请降低并发或稍后重试。"


def transcribe_audio(
    audio_input: str | bytes | Path,
    engine_name: str,
    export_format: str,
    *,
    use_cache: bool = True,
    stopped: Callable[[], bool] | None = None,
) -> str:
    if engine_name not in ENGINE_MAP:
        raise ValueError(f"{engine_name} 不支持本地音频上传识别。")
    engine_cls = ENGINE_MAP[engine_name]
    result = engine_cls(_normalize_audio_input(audio_input), use_cache=use_cache, stopped=stopped).run()
    return export_asr_result(result, export_format)


def export_asr_result(result: object, export_format: str) -> str:
    normalized_format = export_format.lower()
    if normalized_format == "srt":
        return result.to_srt()
    if normalized_format == "ass":
        return result.to_ass()
    return result.to_txt()


def format_task_error(exc: Exception) -> str:
    """Turn any failure into one sentence the user can act on.

    Only messages we wrote ourselves reach the screen. Anything unexpected
    becomes a generic line, and the real exception goes to the log instead.
    """
    message = str(exc).strip()
    if message == STOPPED_MESSAGE:
        return STOPPED_MESSAGE
    if isinstance(exc, UserFacingError):
        return message or GENERIC_MESSAGE

    if isinstance(exc, requests.HTTPError):
        return _http_error_message(exc)
    if isinstance(exc, requests.Timeout):
        return "网络连接超时，请稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return "网络连接失败，请检查网络后重试。"
    if isinstance(exc, requests.RequestException):
        return "网络请求失败，请稍后重试。"

    if isinstance(exc, PermissionError):
        return "文件或目录没有权限，可能正被其他程序占用。"
    if isinstance(exc, FileNotFoundError):
        return "找不到这个文件，可能已被移动或删除。"
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "磁盘空间不足，请清理后重试。"

    _log_unexpected(exc)
    return GENERIC_MESSAGE


def _http_error_message(exc: requests.HTTPError) -> str:
    code = exc.response.status_code if exc.response is not None else 0
    if code == 412:
        return NOT_READY_MESSAGE
    if code in {401, 403}:
        return "识别服务拒绝了这次请求，请检查 API Key 是否正确。"
    if code == 429:
        return "请求过于频繁，请降低并发或稍后重试。"
    if code >= 500:
        return "识别服务暂时不可用，请稍后重试。"
    if code:
        return f"网络请求失败（HTTP {code}），请稍后重试。"
    return "网络请求失败，请稍后重试。"


def _log_unexpected(exc: Exception) -> None:
    try:
        logging.getLogger("bbdown").error("任务失败（未预期的异常）", exc_info=exc)
    except Exception:
        pass


def _normalize_audio_input(audio_input: str | bytes | Path) -> str | bytes:
    if isinstance(audio_input, bytes):
        return audio_input
    return str(audio_input)
