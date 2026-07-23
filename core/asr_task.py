from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.asr_service import format_task_error, transcribe_audio
from core.config import DOUBAO_ENGINE_NAME
from core.doubao_asr import transcribe_doubao_url
from core.media import convert_to_mp3, is_audio
from core.url_audio import audio_name_from_url, fetch_audio_bytes


@dataclass(slots=True)
class ASRTaskResult:
    index: int
    source: str
    status: str
    message: str
    output_path: str = ""


def write_transcript(
    audio_input: str | bytes | Path,
    output_path: Path,
    engine_name: str,
    export_format: str,
    *,
    stopped: Callable[[], bool],
) -> str:
    text = transcribe_audio(audio_input, engine_name, export_format, use_cache=True, stopped=stopped)
    _write_text_atomic(output_path, text, stopped)
    return str(output_path)


def write_url_transcript(
    url: str,
    output_path: Path,
    engine_name: str,
    export_format: str,
    *,
    stopped: Callable[[], bool],
) -> str:
    if engine_name == DOUBAO_ENGINE_NAME:
        text = transcribe_doubao_url(url, export_format, stopped=stopped)
        _write_text_atomic(output_path, text, stopped)
        return str(output_path)

    audio_bytes, _ = fetch_audio_bytes(url, stopped=stopped)
    if stopped():
        raise RuntimeError("已停止")
    text = transcribe_audio(audio_bytes, engine_name, export_format, use_cache=True, stopped=stopped)
    _write_text_atomic(output_path, text, stopped)
    return str(output_path)


def process_file_asr_task(
    *,
    index: int,
    path: str,
    engine_name: str,
    export_format: str,
    output_path: Path,
    ffmpeg_path: str | None,
    stopped: Callable[[], bool],
) -> ASRTaskResult:
    if stopped():
        return ASRTaskResult(index, path, "stopped", "已停止")

    source = Path(path)
    out_path = output_path

    if out_path.exists() and out_path.stat().st_size > 0:
        return ASRTaskResult(index, path, "skip", f"{source.name} -> 已存在", str(out_path))

    audio_path = source
    temp_audio: str | None = None
    if not is_audio(source):
        fd, temp_audio = tempfile.mkstemp(suffix=".mp3", prefix=f"asr_{source.stem[:40]}_")
        os.close(fd)
        if not convert_to_mp3(source, temp_audio, ffmpeg_path, stopped=stopped):
            _remove_temp_audio(temp_audio)
            if stopped():
                return ASRTaskResult(index, path, "stopped", "已停止")
            return ASRTaskResult(index, path, "fail", f"{source.name}: ffmpeg 转音频失败")
        audio_path = Path(temp_audio)

    try:
        if stopped():
            return ASRTaskResult(index, path, "stopped", "已停止")
        output_path = write_transcript(
            audio_path,
            out_path,
            engine_name,
            export_format,
            stopped=stopped,
        )
        return ASRTaskResult(index, path, "ok", f"{source.name} -> {out_path.name}", output_path)
    except Exception as exc:
        return ASRTaskResult(index, path, "fail", f"{source.name}: {format_task_error(exc)}")
    finally:
        if temp_audio:
            _remove_temp_audio(temp_audio)


def process_url_asr_task(
    *,
    index: int,
    url: str,
    engine_name: str,
    export_format: str,
    output_path: Path,
    stopped: Callable[[], bool],
) -> ASRTaskResult:
    if stopped():
        return ASRTaskResult(index, url, "stopped", "已停止")

    stem = audio_name_from_url(url, index)
    out_path = output_path
    if out_path.exists() and out_path.stat().st_size > 0:
        return ASRTaskResult(index, url, "skip", f"{out_path.name} 已存在", str(out_path))

    try:
        output_path = write_url_transcript(
            url,
            out_path,
            engine_name,
            export_format,
            stopped=stopped,
        )
        detail = out_path.name
        return ASRTaskResult(index, url, "ok", detail, output_path)
    except Exception as exc:
        if stopped() and str(exc).strip() == "已停止":
            return ASRTaskResult(index, url, "stopped", "已停止")
        return ASRTaskResult(index, url, "fail", f"{stem}: {format_task_error(exc)}")


def _remove_temp_audio(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _write_text_atomic(output_path: Path, text: str, stopped: Callable[[], bool]) -> None:
    if stopped():
        raise RuntimeError("已停止")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if stopped():
            raise RuntimeError("已停止")
        os.replace(temp_path, output_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
