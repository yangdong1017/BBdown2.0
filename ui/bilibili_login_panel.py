from __future__ import annotations

import locale
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, ComboBox, MessageBox, PushButton

from core.bilibili_workers import LoginWorkerThread
from core.models import LoginResult, Toolchain
from .widgets import CardFrame


class BilibiliLoginPanel(CardFrame):
    status = pyqtSignal(str)
    login_state_changed = pyqtSignal(str)

    def __init__(
        self,
        toolchain: Toolchain,
        runtime_dir: Path,
        save_dir: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.toolchain = toolchain
        self.runtime_dir = runtime_dir
        self.save_dir = save_dir
        self.login_worker: LoginWorkerThread | None = None
        self.download_running = False
        self.qr_mtime: float | None = None
        self.qr_timer = QTimer(self)
        self.qr_timer.timeout.connect(self._refresh_qr_preview)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(BodyLabel("登录二维码", self))

        mode_row = QHBoxLayout()
        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(["WEB 登录", "TV 登录"])
        self.login_btn = PushButton("执行登录", self)
        self.login_btn.clicked.connect(self.start_login)
        mode_row.addWidget(self.mode_combo)
        mode_row.addWidget(self.login_btn)
        layout.addLayout(mode_row)

        self.qr_status_label = CaptionLabel("点击“执行登录”后会在这里显示二维码。", self)
        self.qr_status_label.setWordWrap(True)
        self.qr_status_label.setVisible(False)

        self.qr_image_label = BodyLabel("暂无二维码", self)
        self.qr_image_label.setAlignment(Qt.AlignCenter)
        self.qr_image_label.setMinimumHeight(260)
        self.qr_image_label.setStyleSheet(
            "QLabel { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }"
        )
        layout.addWidget(self.qr_image_label)

        self.login_state_label = CaptionLabel("登录状态: WEB 未登录 | TV 未登录", self)
        self.login_state_label.setWordWrap(True)
        layout.addWidget(self.login_state_label)

    def set_save_dir(self, save_dir: str) -> None:
        self.save_dir = save_dir

    def set_download_running(self, running: bool) -> None:
        self.download_running = running
        if not self.is_running():
            self.login_btn.setEnabled(not running)

    def refresh_login_status(self) -> None:
        base_dir = self.toolchain.bbdown.parent if self.toolchain.bbdown else Path.cwd()
        web_state = "已登录" if (base_dir / "BBDown.data").exists() else "未登录"
        tv_state = "已登录" if (base_dir / "BBDownTV.data").exists() else "未登录"
        state = f"登录状态: WEB {web_state} | TV {tv_state}"
        self.login_state_label.setText(state)
        self.login_state_changed.emit(state)

    def start_login(self) -> None:
        if self.download_running:
            MessageBox("提示", "请先停止当前下载任务，再执行登录。", self.window()).exec()
            return
        if self.is_running():
            MessageBox("提示", "登录流程已经在运行。", self.window()).exec()
            return
        if self.toolchain.bbdown is None:
            MessageBox("提示", "没有找到 BBDown.exe。", self.window()).exec()
            return

        self._clear_qr_preview()
        mode = "web" if "WEB" in self.mode_combo.currentText() else "tv"
        self.qr_status_label.setText("正在获取登录二维码...")

        self.login_worker = LoginWorkerThread(
            mode=mode,
            toolchain=self.toolchain,
            runtime_dir=self.runtime_dir,
            output_encoding=locale.getpreferredencoding(False) or "utf-8",
        )
        self.login_worker.status.connect(self.status.emit)
        self.login_worker.finished_one.connect(self._on_login_finished)
        self.login_worker.start()
        self.login_btn.setEnabled(False)
        self.qr_timer.start(500)

    def stop(self) -> bool:
        if not self.is_running():
            return False
        assert self.login_worker is not None
        self.login_worker.stop()
        self.login_btn.setEnabled(False)
        self.qr_status_label.setText("正在停止登录流程...")
        return True

    def is_running(self) -> bool:
        return bool(self.login_worker and self.login_worker.isRunning())

    def _on_login_finished(self, result: object) -> None:
        assert isinstance(result, LoginResult)
        self.login_worker = None
        self.qr_timer.stop()
        self.login_btn.setEnabled(not self.download_running)
        self.refresh_login_status()
        if result.stopped:
            self.qr_status_label.setText("登录流程已停止。")
        elif result.return_code == 0:
            self.qr_status_label.setText("登录流程已结束，如已确认扫码，登录状态通常会显示为已登录。")
        else:
            self.qr_status_label.setText(f"登录流程结束，退出码 {result.return_code}")

    def _refresh_qr_preview(self) -> None:
        if not self.is_running():
            return
        candidates = (
            self.runtime_dir / "qrcode.png",
            Path(self.save_dir).parent / "qrcode.png",
            Path.cwd() / "qrcode.png",
        )
        for qr_path in candidates:
            if not qr_path.exists():
                continue
            mtime = qr_path.stat().st_mtime
            if self.qr_mtime == mtime:
                return
            pixmap = QPixmap(str(qr_path))
            if pixmap.isNull():
                continue
            scaled = pixmap.scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_image_label.setPixmap(scaled)
            self.qr_image_label.setText("")
            self.qr_status_label.setText("二维码已生成，请用哔哩哔哩 App 扫码并确认。")
            self.qr_mtime = mtime
            return

    def _clear_qr_preview(self) -> None:
        for qr_path in (self.runtime_dir / "qrcode.png", Path.cwd() / "qrcode.png"):
            if qr_path.exists():
                try:
                    qr_path.unlink()
                except OSError:
                    pass
        self.qr_image_label.clear()
        self.qr_image_label.setText("暂无二维码")
        self.qr_status_label.setText("点击“执行登录”后会在这里显示二维码。")
        self.qr_mtime = None
