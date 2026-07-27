from __future__ import annotations

from typing import Protocol


class DouyinMediaLink(Protocol):
    url: str

    @property
    def task_id(self) -> str: ...

    @property
    def file_suffix(self) -> str: ...

    @property
    def content_prefix(self) -> str: ...

    @property
    def media_label(self) -> str: ...
