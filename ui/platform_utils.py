"""Small OS-specific helpers shared by every page."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_directory(path: str | Path) -> bool:
    """Show a folder in the system file manager.

    Returns False when the folder is gone or the system refuses to open it, so
    the caller can tell the user instead of the click doing nothing.
    """
    target = Path(path)
    if not target.is_dir():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except OSError:
        return False
    return True
