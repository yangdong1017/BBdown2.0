"""Shared vocabulary for reading links out of text the user pasted.

Each page decides for itself which links it accepts - that is a product rule,
not something to unify here. What is unified is the plumbing underneath: how a
URL is found in free text, which suffixes count as audio, and which hosts belong
to the Douyin CDN.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar
from urllib.parse import urlparse


URL_PATTERN = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
TRAILING_PUNCTUATION = " \t\r\n\"'<>)]}，。；;、"

AUDIO_SUFFIXES = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg")
DOUYIN_CDN_HOSTS = (
    "douyinstatic.com",
    "douyinvod.com",
    "bytevod.com",
)

T = TypeVar("T")


def iter_urls(text: str) -> Iterator[str]:
    """Yield every URL in the text, with trailing punctuation trimmed off."""
    for match in URL_PATTERN.finditer(text or ""):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        if url:
            yield url


def dedupe(items: Iterable[T], key: Callable[[T], str] | None = None) -> list[T]:
    """Keep the first occurrence of each item and preserve the original order."""
    result: list[T] = []
    seen: set[str] = set()
    for item in items:
        marker = (key(item) if key is not None else str(item)).strip().lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def is_douyin_cdn_host(host: str) -> bool:
    """Match the host itself or any subdomain of it, never a lookalike domain."""
    host = (host or "").lower().strip(".")
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in DOUYIN_CDN_HOSTS)


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()
