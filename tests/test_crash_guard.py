from __future__ import annotations

import logging
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from core import crash_guard


class CrashGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self._temp_dir.name)
        logger = logging.getLogger("bbdown")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        crash_guard._logger = None
        crash_guard._log_path = None
        crash_guard._notified_signatures.clear()
        self._original_excepthook = sys.excepthook
        self._original_thread_excepthook = threading.excepthook

    def tearDown(self) -> None:
        sys.excepthook = self._original_excepthook
        threading.excepthook = self._original_thread_excepthook
        logger = logging.getLogger("bbdown")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        self._temp_dir.cleanup()

    def _read_log(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _raise_and_capture(self, exc: BaseException) -> tuple:
        try:
            raise exc
        except BaseException:
            return sys.exc_info()

    def test_install_replaces_hooks_and_creates_log(self) -> None:
        path = crash_guard.install_crash_guard(self.log_dir)

        self.assertEqual(path, self.log_dir / crash_guard.LOG_FILE_NAME)
        self.assertTrue(path.exists())
        self.assertIs(sys.excepthook, crash_guard.handle_exception)
        self.assertIs(threading.excepthook, crash_guard.handle_thread_exception)

    def test_unhandled_exception_is_logged_and_does_not_raise(self) -> None:
        path = crash_guard.install_crash_guard(self.log_dir)
        exc_type, exc, tb = self._raise_and_capture(NameError("name 'os' is not defined"))

        crash_guard.handle_exception(exc_type, exc, tb)

        content = self._read_log(path)
        self.assertIn("未捕获异常", content)
        self.assertIn("NameError", content)
        self.assertIn("name 'os' is not defined", content)

    def test_missing_log_directory_does_not_break_startup(self) -> None:
        blocked = self.log_dir / "a_file"
        blocked.write_text("not a directory", encoding="utf-8")

        crash_guard.install_crash_guard(blocked / "nested")

        exc_type, exc, tb = self._raise_and_capture(RuntimeError("boom"))
        crash_guard.handle_exception(exc_type, exc, tb)

    def test_keyboard_interrupt_falls_through_to_default_hook(self) -> None:
        crash_guard.install_crash_guard(self.log_dir)
        seen: list[str] = []
        original = sys.__excepthook__
        try:
            sys.__excepthook__ = lambda t, e, tb: seen.append(t.__name__)  # type: ignore[assignment]
            exc_type, exc, tb = self._raise_and_capture(KeyboardInterrupt())
            crash_guard.handle_exception(exc_type, exc, tb)
        finally:
            sys.__excepthook__ = original  # type: ignore[assignment]

        self.assertEqual(seen, ["KeyboardInterrupt"])

    def test_repeated_crash_site_notifies_user_only_once(self) -> None:
        crash_guard.install_crash_guard(self.log_dir)
        shown: list[int] = []
        original_show = crash_guard._show_dialog
        try:
            crash_guard._show_dialog = lambda: shown.append(1)  # type: ignore[assignment]
            for _ in range(3):
                exc_type, exc, tb = self._raise_and_capture(ValueError("same place"))
                crash_guard.handle_exception(exc_type, exc, tb)
        finally:
            crash_guard._show_dialog = original_show  # type: ignore[assignment]

        self.assertEqual(len(shown), 1)
        self.assertIn("ValueError", self._read_log(self.log_dir / crash_guard.LOG_FILE_NAME))

    def test_background_thread_exception_is_logged_without_dialog(self) -> None:
        path = crash_guard.install_crash_guard(self.log_dir)
        shown: list[int] = []
        original_show = crash_guard._show_dialog

        class _Args:
            exc_type = OSError
            exc_value = OSError("disk full")
            exc_traceback = None

        try:
            crash_guard._show_dialog = lambda: shown.append(1)  # type: ignore[assignment]
            crash_guard.handle_thread_exception(_Args())
        finally:
            crash_guard._show_dialog = original_show  # type: ignore[assignment]

        self.assertEqual(shown, [])
        content = self._read_log(path)
        self.assertIn("后台线程未捕获异常", content)
        self.assertIn("disk full", content)


if __name__ == "__main__":
    unittest.main()
