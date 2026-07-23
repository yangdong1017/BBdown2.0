from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import requests

from bk_asr import BcutASR
from core.config import BCUT_ENGINE_NAME


ENGINE_MAP = {
    BCUT_ENGINE_NAME: BcutASR,
}


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
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code == 412:
            return "识别服务结果暂未就绪，已多次重试后仍失败。请降低并发或稍后重试。"
        return f"网络请求失败，HTTP {code}。请稍后重试。"

    message = str(exc).strip()
    if "Precondition Failed" in message or "412" in message:
        return "识别服务结果暂未就绪，已多次重试后仍失败。请降低并发或稍后重试。"
    return message or exc.__class__.__name__


def _normalize_audio_input(audio_input: str | bytes | Path) -> str | bytes:
    if isinstance(audio_input, bytes):
        return audio_input
    return str(audio_input)
