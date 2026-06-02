from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    last_urls: str = ""
    save_dir: str = ""
    thread_count: int = 5
    asr_engine: str = "必剪"
    asr_format: str = "txt"
    asr_concurrency: int = 2
    asr_output_dir: str = ""


@dataclass(slots=True)
class Toolchain:
    bbdown: Path | None = None
    ffmpeg: Path | None = None
    aria2c: Path | None = None
    mp4box: Path | None = None


@dataclass(slots=True)
class DownloadBatchResult:
    stopped: bool
    failed_urls: list[str] = field(default_factory=list)
    no_output_urls: list[str] = field(default_factory=list)
    completed_files: list[str] = field(default_factory=list)
    completed: int = 0
    total: int = 0


@dataclass(slots=True)
class LoginResult:
    mode: str
    stopped: bool
    return_code: int
