from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QWidget


CARD_STYLE = """
QFrame[card="true"] {
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 12px;
}
"""

TEXT_EDIT_STYLE = """
QTextEdit, QPlainTextEdit {
    background-color: #141414;
    color: #f5f7fa;
    selection-background-color: #4cc2ff;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    font-size: 11pt;
}
"""

class CardFrame(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setStyleSheet(CARD_STYLE)
