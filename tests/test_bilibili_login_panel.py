from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.models import LoginResult, Toolchain
from ui.bilibili_login_panel import BilibiliLoginPanel


class _Signal:
    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def emit(self, *args) -> None:
        for slot in self.slots:
            slot(*args)


class _FakeLoginWorker:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.log = _Signal()
        self.status = _Signal()
        self.finished_one = _Signal()
        self.running = False
        self.stopped = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.stopped = True
        self.running = False

    def isRunning(self) -> bool:
        return self.running


class BilibiliLoginPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_owns_login_worker_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            toolchain = Toolchain(bbdown=root / "BBDown.exe")
            sessions: list[str] = []
            logs: list[tuple[str, str]] = []

            with patch("ui.bilibili_login_panel.LoginWorkerThread", _FakeLoginWorker):
                panel = BilibiliLoginPanel(toolchain, root, str(root))
                panel.session_started.connect(sessions.append)
                panel.log.connect(lambda level, message: logs.append((level, message)))
                panel.start_login()

                worker = panel.login_worker
                self.assertIsInstance(worker, _FakeLoginWorker)
                self.assertTrue(panel.is_running())
                self.assertEqual(sessions, ["login"])
                self.assertEqual(worker.kwargs["mode"], "web")
                self.assertTrue(any(level == "info" for level, _ in logs))

                worker.finished_one.emit(LoginResult(mode="web", stopped=False, return_code=0))
                self.assertFalse(panel.is_running())
                self.assertTrue(panel.login_btn.isEnabled())
                panel.deleteLater()

    def test_panel_reports_login_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "BBDown.data").write_text("ready", encoding="utf-8")
            panel = BilibiliLoginPanel(Toolchain(bbdown=root / "BBDown.exe"), root, str(root))
            states: list[str] = []
            panel.login_state_changed.connect(states.append)

            panel.refresh_login_status()

            self.assertEqual(states, ["登录状态: WEB 已登录 | TV 未登录"])
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
