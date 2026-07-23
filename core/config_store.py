from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


_STORE_LOCK = threading.RLock()


def read_json(path: Path) -> dict[str, Any]:
    with _STORE_LOCK:
        return _read_json_unlocked(path)


def update_json(path: Path, **changes: object) -> None:
    if not changes:
        return
    with _STORE_LOCK:
        payload = _read_json_unlocked(path)
        payload.update(changes)
        _write_json_unlocked(path, payload)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    with _STORE_LOCK:
        _write_json_unlocked(path, payload)


def _read_json_unlocked(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_unlocked(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
