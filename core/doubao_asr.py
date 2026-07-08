from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import requests

from core.config import load_doubao_api_key
from core.url_audio import infer_doubao_direct_format


SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = "volc.seedasr.auc"
TEST_AUDIO_URL = "https://lf26-music-east.douyinstatic.com/obj/ies-music-hj/7546439142222302011.mp3"

# 3.1 起不再内置豆包 API Key。正式设置页落地后从本机配置读取。
DOUBAO_API_KEY = ""

SUCCESS_CODE = "20000000"
PROCESSING_CODES = {"20000001", "20000002"}


class DoubaoASRError(RuntimeError):
    pass


def transcribe_doubao_url(
    url: str,
    export_format: str,
    *,
    stopped: Callable[[], bool] | None = None,
    poll_interval: float = 3.0,
    timeout_seconds: int = 30 * 60,
) -> str:
    if export_format.lower() != "txt":
        raise DoubaoASRError("豆包接口当前只输出 txt 文本。")

    api_key = _get_api_key()
    audio_format, content_type = infer_doubao_direct_format(url)
    request_id = str(uuid.uuid4())

    log_id = _submit_task(api_key, request_id, url, audio_format)

    started = time.time()
    while time.time() - started < timeout_seconds:
        if stopped and stopped():
            raise DoubaoASRError("已停止")

        data, status_code, message = _query_task(api_key, request_id, log_id)
        if status_code == SUCCESS_CODE:
            text = _extract_text(data)
            if text:
                return text
            if not data or not data.get("result"):
                time.sleep(poll_interval)
                continue
            else:
                raise DoubaoASRError("豆包识别完成但没有返回文字结果。")

        if status_code in PROCESSING_CODES:
            time.sleep(poll_interval)
            continue

        raise DoubaoASRError(_format_api_error(status_code, message, data))

    detail = f"，链接类型 {content_type}" if content_type else ""
    raise TimeoutError(f"豆包识别等待超时{detail}。")


def test_doubao_api_key(api_key: str, *, timeout_seconds: int = 90) -> bool:
    api_key = api_key.strip()
    if not api_key:
        return False

    try:
        audio_format, _ = infer_doubao_direct_format(TEST_AUDIO_URL)
        request_id = str(uuid.uuid4())
        log_id = _submit_task(api_key, request_id, TEST_AUDIO_URL, audio_format)
        started = time.time()

        while time.time() - started < timeout_seconds:
            data, status_code, message = _query_task(api_key, request_id, log_id)
            if status_code == SUCCESS_CODE:
                return True
            if status_code in PROCESSING_CODES:
                time.sleep(2.0)
                continue
            return False
    except Exception:
        return False

    return False


def _submit_task(api_key: str, request_id: str, url: str, audio_format: str) -> str:
    payload = {
        "user": {"uid": "BBDown2.1"},
        "audio": {
            "url": url,
            "format": audio_format,
            "codec": "raw",
            "rate": 16000,
            "bits": 16,
            "channel": 1,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": False,
            "enable_speaker_info": False,
            "enable_channel_split": False,
            "show_utterances": True,
            "vad_segment": False,
            "sensitive_words_filter": "",
        },
    }
    response = requests.post(
        SUBMIT_URL,
        headers=_headers(api_key, request_id, include_sequence=True),
        json=payload,
        timeout=(10, 30),
    )
    _raise_http_error(response)
    status_code = _response_status_code(response)
    if status_code and status_code != SUCCESS_CODE:
        raise DoubaoASRError(_format_api_error(status_code, _response_message(response), _safe_json(response)))
    return response.headers.get("X-Tt-Logid", "").strip()


def _query_task(api_key: str, request_id: str, log_id: str) -> tuple[dict[str, Any], str, str]:
    response = requests.post(
        QUERY_URL,
        headers=_headers(api_key, request_id, include_sequence=False, log_id=log_id),
        json={},
        timeout=(10, 30),
    )
    _raise_http_error(response)
    data = _safe_json(response)
    status_code = _response_status_code(response) or _data_status_code(data)
    message = _response_message(response) or _data_message(data)
    return data, status_code, message


def _headers(
    api_key: str,
    request_id: str,
    *,
    include_sequence: bool,
    log_id: str = "",
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": request_id,
    }
    if include_sequence:
        headers["X-Api-Sequence"] = "-1"
    if log_id:
        headers["X-Tt-Logid"] = log_id
    return headers


def _extract_text(data: dict[str, Any]) -> str:
    candidates: list[Any] = [
        data.get("text"),
        data.get("result", {}).get("text") if isinstance(data.get("result"), dict) else None,
        data.get("result", {}).get("utterances") if isinstance(data.get("result"), dict) else None,
        data.get("utterances"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, list):
            lines = [
                str(item.get("text", "")).strip()
                for item in candidate
                if isinstance(item, dict) and str(item.get("text", "")).strip()
            ]
            if lines:
                return "\n".join(lines)
    return ""


def _get_api_key() -> str:
    api_key = load_doubao_api_key() or DOUBAO_API_KEY.strip()
    if not api_key:
        raise DoubaoASRError("未配置豆包 API Key，请先到设置页填写。")
    return api_key


def _raise_http_error(response: requests.Response) -> None:
    if response.status_code == 401:
        raise DoubaoASRError("豆包识别失败：API Key 无效或未授权。")
    if response.status_code == 403:
        raise DoubaoASRError("豆包识别失败：服务未开通、资源 ID 无权限或余额不足。")
    if response.status_code >= 500:
        raise DoubaoASRError("豆包识别失败：服务繁忙，请稍后重试。")
    response.raise_for_status()


def _response_status_code(response: requests.Response) -> str:
    return response.headers.get("X-Api-Status-Code", "").strip()


def _response_message(response: requests.Response) -> str:
    return response.headers.get("X-Api-Message", "").strip()


def _data_status_code(data: dict[str, Any]) -> str:
    header = data.get("header")
    if isinstance(header, dict):
        value = header.get("code")
        if value is not None:
            return str(value)
    for key in ("code", "status_code", "statusCode"):
        value = data.get(key)
        if value is not None:
            return str(value)
    return ""


def _data_message(data: dict[str, Any]) -> str:
    header = data.get("header")
    if isinstance(header, dict):
        value = header.get("message")
        if value:
            return str(value)
    for key in ("message", "msg", "error"):
        value = data.get(key)
        if value:
            return str(value)
    return ""


def _format_api_error(status_code: str, message: str, data: dict[str, Any]) -> str:
    raw = message or _data_message(data) or "未知错误"
    lowered = raw.lower()
    if "key" in lowered or "auth" in lowered or "unauthorized" in lowered:
        return "豆包识别失败：API Key 无效或未授权。"
    if "balance" in lowered or "quota" in lowered or "payment" in lowered:
        return "豆包识别失败：余额不足或服务未开通。"
    if "format" in lowered or "audio" in lowered:
        return f"豆包识别失败：音频链接格式不支持。{raw}"
    if status_code:
        return f"豆包识别失败：{raw}（状态码 {status_code}）"
    return f"豆包识别失败：{raw}"


def _safe_json(response: requests.Response) -> dict[str, Any]:
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
