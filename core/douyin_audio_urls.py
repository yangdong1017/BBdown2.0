from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
TRAILING_PUNCTUATION = " \t\r\n\"'<>)]}，。；;、"
AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}
AUDIO_HOST_SUFFIXES = (
    "douyinstatic.com",
    "douyinvod.com",
    "bytevod.com",
)


@dataclass(frozen=True, slots=True)
class DouyinAudioLink:
    audio_id: str
    url: str
    suffix: str

    @property
    def task_id(self) -> str:
        return self.audio_id

    @property
    def file_suffix(self) -> str:
        return self.suffix

    @property
    def content_prefix(self) -> str:
        return "audio/"

    @property
    def media_label(self) -> str:
        return "音频"


def extract_douyin_audio_links(text: str) -> list[DouyinAudioLink]:
    """Extract supported Douyin CDN audio URLs and deduplicate by audio ID."""
    links: list[DouyinAudioLink] = []
    seen: set[str] = set()
    for match in URL_PATTERN.finditer(text or ""):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        suffix = Path(unquote(parsed.path)).suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            continue
        if not any(host == allowed or host.endswith(f".{allowed}") for allowed in AUDIO_HOST_SUFFIXES):
            continue
        audio_id = _safe_id(Path(unquote(parsed.path)).stem)
        if not audio_id:
            continue
        key = audio_id.lower()
        if key in seen:
            continue
        seen.add(key)
        links.append(DouyinAudioLink(audio_id=audio_id, url=url, suffix=suffix))
    return links


def _safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return value[:120].strip("_-")
