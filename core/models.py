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
    asr_concurrency: int = 5
    asr_output_dir: str = ""
    asr_mode: str = "抖音音频链接转文字"
    doubao_api_key: str = ""


@dataclass(slots=True)
class DouyinVideoConfig:
    urls: str = ""
    save_dir: str = ""
    concurrency: int = 5


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
class DouyinVideoBatchResult:
    stopped: bool
    total: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    stopped_count: int = 0
    completed_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    failed_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LoginResult:
    mode: str
    stopped: bool
    return_code: int
