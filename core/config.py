from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .models import AppConfig


IS_FROZEN = getattr(sys, "frozen", False)
APP_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent.parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))

CONFIG_PATH = APP_ROOT / "bbdown_gui_config.json"
LOG_DIR = APP_ROOT / "bbdown_gui_logs"
RUNTIME_DIR = APP_ROOT / "bbdown_runtime"
TOOLS_DIR = APP_ROOT / "bbdown_tools"

THREAD_OPTIONS = (1, 2, 3, 5)
ASR_ENGINE_OPTIONS = ("必剪", "剪映", "快手")
ASR_FORMAT_OPTIONS = ("txt", "srt", "ass")
ASR_CONCURRENCY_OPTIONS = (1, 2, 3, 5)
DEFAULT_THREAD_COUNT = 5
ENABLE_BBDOWN_DEBUG = False
USE_ARIA2C_FOR_DOWNLOAD = True
AUDIO_FILE_PATTERN = "<videoTitle>"
MAX_LOG_LINE_LENGTH = 420
WINDOW_TITLE = "BBDown"


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_app_config() -> AppConfig:
    data = _read_json(CONFIG_PATH)
    thread_count = data.get("thread_count", DEFAULT_THREAD_COUNT)
    try:
        thread_count = int(thread_count)
    except Exception:
        thread_count = DEFAULT_THREAD_COUNT
    if thread_count not in THREAD_OPTIONS:
        thread_count = DEFAULT_THREAD_COUNT

    last_urls = data.get("last_urls") or data.get("last_url") or ""
    if not isinstance(last_urls, str):
        last_urls = ""

    save_dir = data.get("save_dir") or str(Path.home() / "Downloads")
    if not isinstance(save_dir, str):
        save_dir = str(Path.home() / "Downloads")

    asr_engine = data.get("asr_engine") or "必剪"
    if asr_engine not in ASR_ENGINE_OPTIONS:
        asr_engine = "必剪"

    asr_format = data.get("asr_format") or "txt"
    if asr_format not in ASR_FORMAT_OPTIONS:
        asr_format = "txt"

    asr_concurrency = data.get("asr_concurrency") or 2
    try:
        asr_concurrency = int(asr_concurrency)
    except Exception:
        asr_concurrency = 2
    if asr_concurrency not in ASR_CONCURRENCY_OPTIONS:
        asr_concurrency = 2

    asr_output_dir = data.get("asr_output_dir") or ""
    if not isinstance(asr_output_dir, str):
        asr_output_dir = ""

    return AppConfig(
        last_urls=last_urls,
        save_dir=save_dir,
        thread_count=thread_count,
        asr_engine=asr_engine,
        asr_format=asr_format,
        asr_concurrency=asr_concurrency,
        asr_output_dir=asr_output_dir,
    )


def save_app_config(config: AppConfig) -> None:
    payload = {
        "last_urls": config.last_urls,
        "save_dir": config.save_dir,
        "thread_count": config.thread_count,
        "asr_engine": config.asr_engine,
        "asr_format": config.asr_format,
        "asr_concurrency": config.asr_concurrency,
        "asr_output_dir": config.asr_output_dir,
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
