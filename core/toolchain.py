from __future__ import annotations

from pathlib import Path

from .config import APP_ROOT, RESOURCE_ROOT
from .models import Toolchain


def _tool_candidates(tool_name: str) -> list[Path]:
    return [
        APP_ROOT / "tools" / tool_name,
        RESOURCE_ROOT / "tools" / tool_name,
        APP_ROOT / tool_name,
        RESOURCE_ROOT / tool_name,
    ]


def find_tool(tool_name: str) -> Path | None:
    for candidate in _tool_candidates(tool_name):
        if candidate.exists():
            return candidate
    return None


def resolve_toolchain() -> Toolchain:
    return Toolchain(
        bbdown=find_tool("BBDown.exe"),
        ffmpeg=find_tool("ffmpeg.exe"),
        aria2c=find_tool("aria2c.exe"),
        mp4box=find_tool("mp4box.exe"),
    )
