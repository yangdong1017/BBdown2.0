from __future__ import annotations

import re

from .config import (
    ARIA2_CONNECTIONS_PER_TASK,
    AUDIO_FILE_PATTERN,
    BILIBILI_AUDIO_DOWNLOAD,
    BILIBILI_DOWNLOAD_TYPES,
    ENABLE_BBDOWN_DEBUG,
    USE_ARIA2C_FOR_DOWNLOAD,
)
from .models import Toolchain


_BILIBILI_ID_PATTERN = re.compile(r"(?i)(BV[0-9A-Za-z]{10}|av\d+|ep\d+|ss\d+)")


def bilibili_display_id(value: str) -> str:
    match = _BILIBILI_ID_PATTERN.search(value.strip())
    if not match:
        return value.strip()
    video_id = match.group(1)
    return "BV" + video_id[2:] if video_id.lower().startswith("bv") else video_id.lower()


def looks_like_video_input(line: str) -> bool:
    value = line.strip()
    if not value:
        return False
    lower = value.lower()
    return lower.startswith(("http://", "https://", "av", "bv", "ep", "ss"))


def build_aria2_args() -> str:
    connections = ARIA2_CONNECTIONS_PER_TASK
    return f"-x{connections} -s{connections} -j1 -k1M"


def build_download_command(
    url: str,
    save_dir: str,
    toolchain: Toolchain,
    *,
    download_type: str = BILIBILI_AUDIO_DOWNLOAD,
) -> list[str]:
    if toolchain.bbdown is None:
        raise RuntimeError("BBDown.exe not found")
    if download_type not in BILIBILI_DOWNLOAD_TYPES:
        raise ValueError("不支持的B站下载类型")

    command = [
        str(toolchain.bbdown),
        url,
    ]
    if download_type == BILIBILI_AUDIO_DOWNLOAD:
        command.append("--audio-only")
    command.extend(
        [
            "--work-dir",
            save_dir,
            "--file-pattern",
            AUDIO_FILE_PATTERN,
        ]
    )

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
        command.extend(["--aria2c-args", build_aria2_args()])

    return command


def build_login_command(mode: str, toolchain: Toolchain) -> list[str]:
    if toolchain.bbdown is None:
        raise RuntimeError("BBDown.exe not found")
    command_name = "login" if mode == "web" else "logintv"
    return [str(toolchain.bbdown), command_name]
