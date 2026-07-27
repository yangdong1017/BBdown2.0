"""Write result files in a way that never leaves a half-written file behind."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path


def write_text_atomic(
    output_path: Path,
    text: str,
    stopped: Callable[[], bool] | None = None,
) -> None:
    """Write the text to a temporary file first, then swap it into place.

    ``stopped`` is checked before and after writing so a cancelled task does not
    leave a truncated transcript on disk.
    """
    _check_stopped(stopped)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _check_stopped(stopped)
        os.replace(temporary_name, output_path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _check_stopped(stopped: Callable[[], bool] | None) -> None:
    if stopped is not None and stopped():
        raise RuntimeError("已停止")
