from __future__ import annotations

import subprocess
import sys
from pathlib import Path


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | {".mp4", ".mkv", ".flv", ".mov", ".avi", ".wmv", ".ts", ".webm", ".rmvb"}


def is_audio(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTENSIONS


def is_media(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MEDIA_EXTENSIONS


def convert_to_mp3(input_file: str | Path, output_file: str | Path, ffmpeg_path: str | Path | None) -> bool:
    if ffmpeg_path is None:
        return False

    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg_path),
        "-i",
        str(input_file),
        "-ac",
        "1",
        "-f",
        "mp3",
        "-af",
        "aresample=async=1",
        "-y",
        str(output),
    ]
    kwargs: dict[str, object] = {
        "capture_output": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(command, **kwargs)
    except (FileNotFoundError, OSError):
        return False
    return result.returncode == 0 and output.is_file() and output.stat().st_size > 0
