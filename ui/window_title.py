"""Keep the title bar in sync with whatever batch is running."""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget

from core.config import WINDOW_TITLE


def set_task_title(widget: QWidget, text: str = "") -> None:
    """Show batch progress in the title bar.

    Call with no text when the batch ends, so the title never stays stuck on a
    finished job while the user is doing something else.
    """
    window = widget.window()
    if window is None:
        return
    window.setWindowTitle(f"BBDown - {text}" if text else WINDOW_TITLE)
