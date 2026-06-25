from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.asr_service import format_task_error, transcribe_audio
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
) -> str:
    text = transcribe_audio(audio_input, engine_name, export_format, use_cache=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return str(output_path)


def process_file_asr_task(
    *,
    index: int,
    path: str,
    engine_name: str,
    export_format: str,
    out_dir: str,
    ffmpeg_path: str | None,
    stopped: Callable[[], bool],
) -> ASRTaskResult:
    if stopped():
        return ASRTaskResult(index, path, "stopped", "已停止")

    source = Path(path)
    target_dir = Path(out_dir) if out_dir else source.parent
    out_path = target_dir / f"{source.stem}.{export_format.lower()}"

    if out_path.exists() and out_path.stat().st_size > 0:
        return ASRTaskResult(index, path, "skip", f"{source.name} -> 已存在", str(out_path))

    audio_path = source
    temp_audio: str | None = None
    if not is_audio(source):
        fd, temp_audio = tempfile.mkstemp(suffix=".mp3", prefix=f"asr_{source.stem[:40]}_")
        os.close(fd)
        if not convert_to_mp3(source, temp_audio, ffmpeg_path):
            _remove_temp_audio(temp_audio)
            return ASRTaskResult(index, path, "fail", f"{source.name}: ffmpeg 转音频失败")
        audio_path = Path(temp_audio)

    try:
        if stopped():
            return ASRTaskResult(index, path, "stopped", "已停止")
        output_path = write_transcript(audio_path, out_path, engine_name, export_format)
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
    out_dir: Path,
    stopped: Callable[[], bool],
) -> ASRTaskResult:
    if stopped():
        return ASRTaskResult(index, url, "stopped", "已停止")

    stem = audio_name_from_url(url, index)
    out_path = out_dir / f"{stem}.{export_format.lower()}"
    if out_path.exists() and out_path.stat().st_size > 0:
        return ASRTaskResult(index, url, "skip", f"{out_path.name} 已存在", str(out_path))

    try:
        audio_bytes, content_type = fetch_audio_bytes(url)
        if stopped():
            return ASRTaskResult(index, url, "stopped", "已停止")

        output_path = write_transcript(audio_bytes, out_path, engine_name, export_format)
        detail = out_path.name
        if content_type:
            detail = f"{detail} | {content_type}"
        return ASRTaskResult(index, url, "ok", detail, output_path)
    except Exception as exc:
        return ASRTaskResult(index, url, "fail", f"{stem}: {format_task_error(exc)}")


def _remove_temp_audio(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
