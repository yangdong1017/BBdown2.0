from __future__ import annotations

import logging
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any


LOG_FILE_NAME = "bbdown.log"
MAX_LOG_BYTES = 1024 * 1024
LOG_BACKUP_COUNT = 2

_USER_MESSAGE = (
    "软件遇到了一个没预料到的问题，已经记录下来。\n"
    "正在运行的任务不受影响，可以继续使用。\n\n"
    "如果反复出现，把下面这个日志文件发给作者：\n{log_path}"
)

_logger: logging.Logger | None = None
_log_path: Path | None = None
_notify_lock = threading.Lock()
_notified_signatures: set[str] = set()
_dialog_visible = False


def setup_logging(log_dir: Path) -> Path:
    """Create the rotating log file and return its path."""
    global _logger, _log_path

    path = Path(log_dir) / LOG_FILE_NAME
    logger = logging.getLogger("bbdown")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler: logging.Handler
        try:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                path,
                maxBytes=MAX_LOG_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
            )
        except OSError:
            # A read-only or missing directory must never stop the app from starting.
            handler = logging.NullHandler()
        logger.addHandler(handler)

    _logger = logger
    _log_path = path
    return path


def install_crash_guard(log_dir: Path) -> Path:
    """Log unhandled exceptions instead of letting PyQt abort the process."""
    path = setup_logging(log_dir)
    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
    return path


def get_log_path() -> Path | None:
    return _log_path


def handle_exception(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return

    _log_exception("未捕获异常", exc_type, exc, tb)
    _notify_user(exc_type, exc, tb)


def handle_thread_exception(args: Any) -> None:
    exc_type = getattr(args, "exc_type", None)
    if exc_type is None or issubclass(exc_type, SystemExit):
        return
    _log_exception(
        "后台线程未捕获异常",
        exc_type,
        getattr(args, "exc_value", None),
        getattr(args, "exc_traceback", None),
    )


def _log_exception(
    title: str,
    exc_type: type[BaseException],
    exc: BaseException | None,
    tb: TracebackType | None,
) -> None:
    detail = "".join(traceback.format_exception(exc_type, exc, tb)).strip()
    logger = _logger or logging.getLogger("bbdown")
    try:
        logger.error("%s\n%s", title, detail)
    except Exception:
        pass


def _exception_signature(exc_type: type[BaseException], tb: TracebackType | None) -> str:
    frames = traceback.extract_tb(tb)
    if not frames:
        return exc_type.__name__
    last = frames[-1]
    return f"{exc_type.__name__}@{last.filename}:{last.lineno}"


def _notify_user(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> None:
    """Show one dark-themed dialog per distinct crash site, main thread only."""
    global _dialog_visible

    if threading.current_thread() is not threading.main_thread():
        return

    signature = _exception_signature(exc_type, tb)
    with _notify_lock:
        if _dialog_visible or signature in _notified_signatures:
            return
        _notified_signatures.add(signature)
        _dialog_visible = True

    try:
        _show_dialog()
    except Exception:
        pass
    finally:
        with _notify_lock:
            _dialog_visible = False


def _show_dialog() -> None:
    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import MessageBox

    app = QApplication.instance()
    if app is None:
        return

    parent = QApplication.activeWindow()
    if parent is None:
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible():
                parent = widget
                break
    if parent is None:
        return

    box = MessageBox(
        "操作没能完成",
        _USER_MESSAGE.format(log_path=_log_path or LOG_FILE_NAME),
        parent,
    )
    box.yesButton.setText("知道了")
    box.cancelButton.hide()
    box.buttonLayout.insertStretch(1)
    box.exec()
