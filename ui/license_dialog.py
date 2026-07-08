from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, LineEdit, PrimaryPushButton, PushButton, TitleLabel

from core.config import APP_VERSION
from core.license_service import LicenseService


class LicenseDialog(QDialog):
    def __init__(self, license_service: LicenseService, parent=None) -> None:
        super().__init__(parent)
        self.license_service = license_service
        self.setWindowTitle(f"BBDown{APP_VERSION} 激活")
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(460, 230)
        self.setStyleSheet(
            """
            QDialog {
                background: #202020;
                color: #f5f7fa;
            }
            """
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(TitleLabel("软件激活", self))
        layout.addWidget(CaptionLabel("请输入卡密，激活后会自动绑定当前设备。", self))

        self.key_edit = LineEdit(self)
        self.key_edit.setPlaceholderText("请输入卡密")
        self.key_edit.setClearButtonEnabled(True)
        self.key_edit.returnPressed.connect(self._activate)
        layout.addWidget(self.key_edit)

        self.status_label = BodyLabel("", self)
        self.status_label.setStyleSheet("color: #ff6a5c;")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.exit_btn = PushButton("退出", self)
        self.exit_btn.clicked.connect(self.reject)
        self.activate_btn = PrimaryPushButton("激活", self)
        self.activate_btn.clicked.connect(self._activate)
        button_row.addWidget(self.exit_btn)
        button_row.addWidget(self.activate_btn)
        layout.addLayout(button_row)

    def _activate(self) -> None:
        card_key = self.key_edit.text().strip()
        if not card_key:
            self._set_status("请输入卡密", ok=False)
            return

        self._set_busy(True)
        self._set_status("正在激活...", ok=True)
        result = self.license_service.activate(card_key)
        self._set_busy(False)
        if result.ok:
            self._set_status("激活成功", ok=True)
            self.accept()
            return
        self._set_status(result.message, ok=False)

    def _set_busy(self, busy: bool) -> None:
        self.key_edit.setEnabled(not busy)
        self.activate_btn.setEnabled(not busy)
        self.exit_btn.setEnabled(not busy)

    def _set_status(self, text: str, *, ok: bool) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {'#7fd26f' if ok else '#ff6a5c'};")
