from __future__ import annotations

import shlex

from .config import AUDIO_FILE_PATTERN, ENABLE_BBDOWN_DEBUG, USE_ARIA2C_FOR_DOWNLOAD
from .models import Toolchain


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def looks_like_video_input(line: str) -> bool:
    value = line.strip()
    if not value:
        return False
    lower = value.lower()
    return lower.startswith(("http://", "https://", "av", "bv", "ep", "ss"))


def build_aria2_args(thread_count: int) -> str:
    return f"-x{thread_count} -s{thread_count} -j{thread_count} -k1M"


def build_download_command(url: str, save_dir: str, thread_count: int, toolchain: Toolchain) -> list[str]:
    if toolchain.bbdown is None:
        raise RuntimeError("BBDown.exe not found")

    command = [
        str(toolchain.bbdown),
        url,
        "--audio-only",
        "--work-dir",
        save_dir,
        "--file-pattern",
        AUDIO_FILE_PATTERN,
    ]

    if ENABLE_BBDOWN_DEBUG:
        command.append("--debug")

    if toolchain.ffmpeg is not None:
        command.extend(["--ffmpeg-path", str(toolchain.ffmpeg)])
    elif toolchain.mp4box is not None:
        command.append("--use-mp4box")
        command.extend(["--mp4box-path", str(toolchain.mp4box)])

    if USE_ARIA2C_FOR_DOWNLOAD and toolchain.aria2c is not None:
        command.append("--use-aria2c")
        command.extend(["--aria2c-path", str(toolchain.aria2c)])
        command.extend(["--aria2c-args", build_aria2_args(thread_count)])

    return command


def build_login_command(mode: str, toolchain: Toolchain) -> list[str]:
    if toolchain.bbdown is None:
        raise RuntimeError("BBDown.exe not found")
    command_name = "login" if mode == "web" else "logintv"
    return [str(toolchain.bbdown), command_name]
