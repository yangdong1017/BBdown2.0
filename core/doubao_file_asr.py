from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.atomic_io import write_text_atomic
from core.doubao_asr import transcribe_doubao_url
from core.tos_public_storage import PublicTOSObject, PublicTOSStorage


MEDIA_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".wma": "audio/x-ms-wma",
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".flv": "video/x-flv",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv",
    ".ts": "video/mp2t",
    ".webm": "video/webm",
    ".rmvb": "application/vnd.rn-realmedia-vbr",
}


class DoubaoFileASRError(RuntimeError):
    pass


@dataclass(slots=True)
class DoubaoFileASRResult:
    output_path: str
    cleanup_ok: bool = True


def transcribe_doubao_file(
    source: str | Path,
    output_path: Path,
    *,
    stopped: Callable[[], bool],
    status_callback: Callable[[str], None] | None = None,
    storage: PublicTOSStorage | None = None,
) -> DoubaoFileASRResult:
    source_path = Path(source)
    storage = storage or PublicTOSStorage()
    uploaded: PublicTOSObject | None = None
    completed: DoubaoFileASRResult | None = None

    try:
        suffix = source_path.suffix.lower()
        content_type = MEDIA_CONTENT_TYPES.get(suffix)
        if content_type is None:
            raise DoubaoFileASRError("暂不支持这个音视频格式。")

        _check_stopped(stopped)
        _emit_status(status_callback, "上传中")
        uploaded = storage.upload(
            source_path,
            suffix=suffix,
            content_type=content_type,
            stopped=stopped,
        )

        _check_stopped(stopped)
        _emit_status(status_callback, "识别中")
        text = transcribe_doubao_url(uploaded.url, "txt", stopped=stopped, infer_format=False)
        write_text_atomic(output_path, text, stopped)
        completed = DoubaoFileASRResult(str(output_path))
    finally:
        if uploaded is not None:
            try:
                cleanup_ok = storage.delete(uploaded)
            except Exception:
                cleanup_ok = False
            if completed is not None:
                completed.cleanup_ok = cleanup_ok

    if completed is None:
        raise DoubaoFileASRError("豆包转文字未完成。")
    return completed


def _check_stopped(stopped: Callable[[], bool]) -> None:
    if stopped():
        raise DoubaoFileASRError("已停止")


def _emit_status(callback: Callable[[str], None] | None, status: str) -> None:
    if callback is not None:
        callback(status)
