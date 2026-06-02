from __future__ import annotations

import time

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QWidget

from qfluentwidgets import TextEdit


CARD_STYLE = """
QFrame[card="true"] {
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 12px;
}
"""

TEXT_EDIT_STYLE = """
QTextEdit {
    background-color: #141414;
    color: #f5f7fa;
    selection-background-color: #4cc2ff;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    font-size: 11pt;
}
"""

LOG_STYLE = """
QTextEdit {
    background-color: #111111;
    color: #d4d4d4;
    font-family: Consolas, 'Courier New', monospace;
    selection-background-color: #4cc2ff;
    font-size: 9pt;
    border: 1px solid #262626;
    border-radius: 8px;
}
"""

LEVEL_COLORS = {
    "info": "#d4d4d4",
    "ok": "#7fd26f",
    "skip": "#6aaee6",
    "warn": "#e5b84a",
    "fail": "#ff6a5c",
}


class CardFrame(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setStyleSheet(CARD_STYLE)


class ConsoleLog(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = TextEdit(self)
        self.edit.setReadOnly(True)
        self.edit.setStyleSheet(LOG_STYLE)
        layout.addWidget(self.edit)

    def log(self, level: str, message: str) -> None:
        color = LEVEL_COLORS.get(level, LEVEL_COLORS["info"])
        safe = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.edit.append(f'<span style="color:{color}">[{time.strftime("%H:%M:%S")}] {safe}</span>')

    def clear(self) -> None:
        self.edit.clear()
