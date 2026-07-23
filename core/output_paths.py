from __future__ import annotations

import os
import threading
from pathlib import Path


class OutputPathAllocator:
    """Reserves unique output paths for one concurrent batch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reserved: set[str] = set()

    def reserve(self, target: Path, *, allow_existing: bool = False) -> Path:
        with self._lock:
            if allow_existing and not self._is_reserved(target):
                self._mark_reserved(target)
                return target

            candidate = target
            counter = 2
            while candidate.exists() or self._is_reserved(candidate):
                candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
                counter += 1
            self._mark_reserved(candidate)
            return candidate

    def _is_reserved(self, path: Path) -> bool:
        return _path_key(path) in self._reserved

    def _mark_reserved(self, path: Path) -> None:
        self._reserved.add(_path_key(path))


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
