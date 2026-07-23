from __future__ import annotations

import re
from dataclasses import dataclass


PLAY_URL_PATTERN = re.compile(
    r"https://aweme\.snssdk\.com/aweme/v1/play/\?video_id=([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DouyinVideoLink:
    video_id: str
    url: str


def extract_douyin_video_links(text: str) -> list[DouyinVideoLink]:
    """Extract supported play URLs from arbitrary pasted text and deduplicate by video ID."""
    links: list[DouyinVideoLink] = []
    seen: set[str] = set()
    for match in PLAY_URL_PATTERN.finditer(text or ""):
        video_id = match.group(1)
        key = video_id.lower()
        if key in seen:
            continue
        seen.add(key)
        links.append(
            DouyinVideoLink(
                video_id=video_id,
                url=f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}",
            )
        )
    return links
