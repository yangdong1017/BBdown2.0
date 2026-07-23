from __future__ import annotations

import os
import sys
from pathlib import Path

from .config_store import read_json, update_json
from .models import AppConfig, DouyinVideoConfig


IS_FROZEN = getattr(sys, "frozen", False)
APP_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent.parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))

CONFIG_PATH = APP_ROOT / "bbdown_gui_config.json"
LICENSE_PATH = APP_ROOT / "bbdown_license.json"
LOG_DIR = APP_ROOT / "bbdown_gui_logs"
RUNTIME_DIR = APP_ROOT / "bbdown_runtime"
TOOLS_DIR = APP_ROOT / "bbdown_tools"

APP_VERSION = "4.0"
MIN_CONCURRENCY = 5
THREAD_OPTIONS = (5, 8, 10)
DOUYIN_VIDEO_CONCURRENCY_OPTIONS = (5, 10, 20)
BCUT_ENGINE_NAME = "必剪"
DOUBAO_ENGINE_NAME = "豆包"
ASR_ENGINE_OPTIONS = (BCUT_ENGINE_NAME, DOUBAO_ENGINE_NAME)
LOCAL_FILE_ASR_ENGINE_OPTIONS = (BCUT_ENGINE_NAME,)
ASR_FORMAT_OPTIONS = ("txt", "srt", "ass")
ASR_CONCURRENCY_OPTIONS = (5, 8, 10)
DOUBAO_ASR_CONCURRENCY_OPTIONS = (5, 8, 10, 30, 50)
ALL_ASR_CONCURRENCY_OPTIONS = tuple(sorted(set(ASR_CONCURRENCY_OPTIONS + DOUBAO_ASR_CONCURRENCY_OPTIONS)))
ASR_MODE_OPTIONS = ("抖音音频链接转文字", "音视频转文字")
DEFAULT_THREAD_COUNT = 5
DEFAULT_DOUYIN_VIDEO_CONCURRENCY = 5
DEFAULT_ASR_CONCURRENCY = 5
DOUYIN_VIDEO_CHUNK_SIZE = 1024 * 1024
DOUYIN_VIDEO_RETRY_COUNT = 3
DOUYIN_VIDEO_TIMEOUT = (10, 30)
ENABLE_BBDOWN_DEBUG = False
USE_ARIA2C_FOR_DOWNLOAD = True
AUDIO_FILE_PATTERN = "<videoTitle>"
MAX_LOG_LINE_LENGTH = 420
WINDOW_TITLE = f"BBDown {APP_VERSION}"

# Empty LICENSE_API_URL means the app uses core/license_private.py to connect Feishu Base directly.
# Direct mode is simple to package, but the bundled EXE may expose Feishu credentials if reversed.
DEFAULT_LICENSE_API_URL = ""
LICENSE_API_URL = os.getenv("BBDOWN_LICENSE_API_URL", DEFAULT_LICENSE_API_URL).strip().rstrip("/")
LICENSE_REQUIRED = os.getenv("BBDOWN_LICENSE_REQUIRED", "1").strip().lower() in {"1", "true", "yes", "on"}
LICENSE_VERIFY_INTERVAL_HOURS = 24
LICENSE_OFFLINE_GRACE_HOURS = 72


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)


def load_app_config() -> AppConfig:
    data = read_json(CONFIG_PATH)
    thread_count = _normalize_concurrency(
        data.get("thread_count", DEFAULT_THREAD_COUNT),
        options=THREAD_OPTIONS,
        default=DEFAULT_THREAD_COUNT,
    )

    last_urls = data.get("last_urls") or data.get("last_url") or ""
    if not isinstance(last_urls, str):
        last_urls = ""

    save_dir = data.get("save_dir") or str(Path.home() / "Downloads")
    if not isinstance(save_dir, str):
        save_dir = str(Path.home() / "Downloads")

    asr_engine = data.get("asr_engine") or BCUT_ENGINE_NAME
    if asr_engine not in ASR_ENGINE_OPTIONS:
        asr_engine = BCUT_ENGINE_NAME

    asr_format = data.get("asr_format") or "txt"
    if asr_format not in ASR_FORMAT_OPTIONS:
        asr_format = "txt"

    asr_concurrency = _normalize_concurrency(
        data.get("asr_concurrency", DEFAULT_ASR_CONCURRENCY),
        options=ALL_ASR_CONCURRENCY_OPTIONS,
        default=DEFAULT_ASR_CONCURRENCY,
    )

    asr_output_dir = data.get("asr_output_dir") or ""
    if not isinstance(asr_output_dir, str):
        asr_output_dir = ""

    asr_mode = data.get("asr_mode") or "抖音音频链接转文字"
    if asr_mode == "抖音链接转文字":
        asr_mode = "抖音音频链接转文字"
    if asr_mode not in ASR_MODE_OPTIONS:
        asr_mode = "抖音音频链接转文字"

    doubao_api_key = data.get("doubao_api_key") or ""
    if not isinstance(doubao_api_key, str):
        doubao_api_key = ""

    return AppConfig(
        last_urls=last_urls,
        save_dir=save_dir,
        thread_count=thread_count,
        asr_engine=asr_engine,
        asr_format=asr_format,
        asr_concurrency=asr_concurrency,
        asr_output_dir=asr_output_dir,
        asr_mode=asr_mode,
        doubao_api_key=doubao_api_key.strip(),
    )


def update_app_config(**changes: object) -> None:
    allowed_keys = {
        "last_urls",
        "save_dir",
        "thread_count",
        "asr_engine",
        "asr_format",
        "asr_concurrency",
        "asr_output_dir",
        "asr_mode",
        "doubao_api_key",
    }
    unknown_keys = set(changes) - allowed_keys
    if unknown_keys:
        names = ", ".join(sorted(unknown_keys))
        raise ValueError(f"未知配置项: {names}")

    normalized = dict(changes)
    if "thread_count" in normalized:
        normalized["thread_count"] = _normalize_concurrency(
            normalized["thread_count"],
            options=THREAD_OPTIONS,
            default=DEFAULT_THREAD_COUNT,
        )
    if "asr_concurrency" in normalized:
        normalized["asr_concurrency"] = _normalize_concurrency(
            normalized["asr_concurrency"],
            options=ALL_ASR_CONCURRENCY_OPTIONS,
            default=DEFAULT_ASR_CONCURRENCY,
        )
    if "doubao_api_key" in normalized:
        normalized["doubao_api_key"] = str(normalized["doubao_api_key"]).strip()
    update_json(CONFIG_PATH, **normalized)


def load_douyin_video_config() -> DouyinVideoConfig:
    data = read_json(CONFIG_PATH)
    urls = data.get("douyin_video_urls") or ""
    if not isinstance(urls, str):
        urls = ""

    default_dir = str(Path.home() / "Downloads" / "抖音视频")
    save_dir = data.get("douyin_video_save_dir") or default_dir
    if not isinstance(save_dir, str):
        save_dir = default_dir

    concurrency = _normalize_concurrency(
        data.get("douyin_video_concurrency", DEFAULT_DOUYIN_VIDEO_CONCURRENCY),
        options=DOUYIN_VIDEO_CONCURRENCY_OPTIONS,
        default=DEFAULT_DOUYIN_VIDEO_CONCURRENCY,
    )
    return DouyinVideoConfig(urls=urls, save_dir=save_dir, concurrency=concurrency)


def save_douyin_video_config(config: DouyinVideoConfig) -> None:
    concurrency = _normalize_concurrency(
        config.concurrency,
        options=DOUYIN_VIDEO_CONCURRENCY_OPTIONS,
        default=DEFAULT_DOUYIN_VIDEO_CONCURRENCY,
    )
    update_json(
        CONFIG_PATH,
        douyin_video_urls=config.urls,
        douyin_video_save_dir=config.save_dir,
        douyin_video_concurrency=concurrency,
    )


def load_doubao_api_key() -> str:
    data = read_json(CONFIG_PATH)
    api_key = data.get("doubao_api_key") or ""
    return api_key.strip() if isinstance(api_key, str) else ""


def save_doubao_api_key(api_key: str) -> None:
    update_app_config(doubao_api_key=api_key)


def _normalize_concurrency(value: object, *, options: tuple[int, ...], default: int) -> int:
    try:
        normalized = int(value)
    except Exception:
        return default
    if normalized < MIN_CONCURRENCY:
        return MIN_CONCURRENCY
    if normalized not in options:
        return default
    return normalized
