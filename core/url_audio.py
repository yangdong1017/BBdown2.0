from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests


URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
AUDIO_SUFFIXES = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg")
DOUBAO_DIRECT_SUFFIXES = {
    ".mp3": "mp3",
    ".wav": "wav",
}
AUDIO_PATH_HINTS = (
    "/ies-music",
    "/obj/ies-music",
    "/tos-cn-ve-",
    "/tos-cn-i-",
)
AUDIO_HOST_HINTS = (
    "douyinstatic.com",
    "douyinvod.com",
    "bytevod.com",
)
DOUYIN_SHARE_HOST_HINTS = (
    "v.douyin.com",
    "www.douyin.com",
    "m.douyin.com",
    "iesdouyin.com",
)
DOUYIN_SHARE_PATH_HINTS = (
    "/video/",
    "/note/",
    "/share/video/",
    "/share/note/",
)
TRAILING_PUNCTUATION = " \t\r\n\"'<>)]}，。；;、"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
}


class AudioUrlError(RuntimeError):
    pass


def extract_audio_urls(text: str) -> list[str]:
    """Extract direct audio URLs from pasted text while preserving order."""
    if not text:
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        if not _looks_like_audio_url(url):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(url)
    return urls


def extract_douyin_share_urls(text: str) -> list[str]:
    """Extract Douyin video/note share URLs that are not direct audio URLs."""
    if not text:
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        if _looks_like_audio_url(url) or not _looks_like_douyin_share_url(url):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        urls.append(url)
    return urls


def _looks_like_audio_url(url: str) -> bool:
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()
    host = parsed.netloc.lower()
    if path.endswith(AUDIO_SUFFIXES):
        return True
    if any(host_hint in host for host_hint in AUDIO_HOST_HINTS):
        return any(path_hint in path for path_hint in AUDIO_PATH_HINTS)
    return False


def _looks_like_douyin_share_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = unquote(parsed.path).lower()
    if not any(host_hint in host for host_hint in DOUYIN_SHARE_HOST_HINTS):
        return False
    if "v.douyin.com" in host:
        return True
    return any(path_hint in path for path_hint in DOUYIN_SHARE_PATH_HINTS)


def audio_name_from_url(url: str, index: int) -> str:
    parsed = urlparse(url)
    filename = unquote(Path(parsed.path).name)
    stem = Path(filename).stem if filename else ""
    stem = _safe_stem(stem)
    return stem or f"audio_url_{index + 1:04d}"


def audio_filename_from_url(url: str, index: int) -> str:
    """Return a safe display filename while keeping a known audio suffix."""
    parsed = urlparse(url)
    raw_name = unquote(Path(parsed.path).name)
    suffix = Path(raw_name).suffix.lower() if raw_name else ""
    if suffix not in AUDIO_SUFFIXES:
        suffix = ""
    return f"{audio_name_from_url(url, index)}{suffix}"


def probe_audio_size(
    url: str,
    *,
    timeout: tuple[int, int] = (5, 10),
    stopped: Callable[[], bool] | None = None,
) -> int | None:
    """Read the remote audio size without downloading the whole file."""
    if stopped and stopped():
        raise AudioUrlError("已停止")

    response = None
    try:
        response = requests.head(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        size = _positive_content_length(response.headers.get("content-length"))
        if size is not None:
            return size
    except requests.RequestException:
        pass
    finally:
        if response is not None:
            response.close()

    if stopped and stopped():
        raise AudioUrlError("已停止")

    headers = dict(DEFAULT_HEADERS)
    headers["Range"] = "bytes=0-0"
    with requests.get(
        url,
        headers=headers,
        timeout=timeout,
        allow_redirects=True,
        stream=True,
    ) as response:
        response.raise_for_status()
        content_range = response.headers.get("content-range", "")
        if "/" in content_range:
            total_text = content_range.rsplit("/", 1)[-1].strip()
            size = _positive_content_length(total_text)
            if size is not None:
                return size
        if response.status_code != 206:
            return _positive_content_length(response.headers.get("content-length"))
    return None


def fetch_audio_bytes(
    url: str,
    *,
    timeout: tuple[int, int] = (10, 120),
    max_bytes: int = 120 * 1024 * 1024,
    stopped: Callable[[], bool] | None = None,
) -> tuple[bytes, str]:
    with requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, stream=True) as response:
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type.lower():
            raise AudioUrlError("链接返回的是网页，不是音频文件")

        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise AudioUrlError(f"音频过大，超过 {max_bytes // (1024 * 1024)} MB")
            except ValueError:
                pass

        data = bytearray()
        total = 0
        for chunk in response.iter_content(chunk_size=1024 * 512):
            if stopped and stopped():
                raise AudioUrlError("已停止")
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise AudioUrlError(f"音频过大，超过 {max_bytes // (1024 * 1024)} MB")
            data.extend(chunk)

    if not data:
        raise AudioUrlError("没有读取到音频内容")
    return bytes(data), content_type


def infer_doubao_direct_format(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    suffix = Path(unquote(parsed.path)).suffix.lower()
    if suffix in DOUBAO_DIRECT_SUFFIXES:
        return DOUBAO_DIRECT_SUFFIXES[suffix], ""
    if suffix in AUDIO_SUFFIXES:
        raise AudioUrlError("豆包直链模式暂只支持 mp3/wav，这条链接不是可直接识别的 mp3/wav。")

    content_type = probe_audio_content_type(url)
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type in {"audio/mpeg", "audio/mp3"}:
        return "mp3", content_type
    if normalized_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return "wav", content_type
    if normalized_type in {"audio/mp4", "audio/aac", "audio/x-m4a"}:
        raise AudioUrlError("豆包直链模式暂只支持 mp3/wav，这条链接是 audio/mp4/m4a，不能直接提交。")
    raise AudioUrlError("无法判断这条链接是否为 mp3/wav，豆包直链模式暂不处理。")


def probe_audio_content_type(url: str, *, timeout: tuple[int, int] = (8, 20)) -> str:
    try:
        response = requests.head(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
        if response.ok:
            content_type = response.headers.get("content-type", "")
            if content_type:
                return content_type
    except requests.RequestException:
        pass

    headers = dict(DEFAULT_HEADERS)
    headers["Range"] = "bytes=0-0"
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type.lower():
            raise AudioUrlError("链接返回的是网页，不是音频文件")
        return content_type


def _safe_stem(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    value = re.sub(r"\s+", "_", value)
    return value[:120].strip("._- ")


def _positive_content_length(value: str | None) -> int | None:
    try:
        size = int(value or "")
    except (TypeError, ValueError):
        return None
    return size if size > 0 else None
