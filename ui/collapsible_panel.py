"""The sliding right-hand panel shared by the download pages."""

from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, ToolButton


PANEL_WIDTH = 400
ANIMATION_MS = 220


class CollapsibleRightPanel(QWidget):
    """A settings column with a slim button that slides it in and out.

    Put page content into ``content_layout``. Width and speed are constructor
    arguments so a page can differ without a new class.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        width: int = PANEL_WIDTH,
        duration_ms: int = ANIMATION_MS,
        spacing: int = 14,
    ) -> None:
        super().__init__(parent)
        self._width = width

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.toggle_button = ToolButton(self)
        self.toggle_button.setIcon(FIF.CARE_RIGHT_SOLID)
        self.toggle_button.setFixedSize(26, 72)
        self.toggle_button.setToolTip("收起右侧面板")
        self.toggle_button.clicked.connect(self.toggle)
        row.addWidget(self.toggle_button, 0, Qt.AlignVCenter)

        self.content = QWidget(self)
        self.content.setMinimumWidth(0)
        self.content.setMaximumWidth(width)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(spacing)
        row.addWidget(self.content)

        self.is_expanded = True
        self.animation = QPropertyAnimation(self.content, b"maximumWidth", self)
        self.animation.setDuration(duration_ms)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self._on_animation_finished)

    def toggle(self) -> None:
        self.animation.stop()
        start_width = self.content.width()
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.content.setVisible(True)
            self.toggle_button.setIcon(FIF.CARE_RIGHT_SOLID)
            self.toggle_button.setToolTip("收起右侧面板")
            target_width = self._width
        else:
            self.toggle_button.setIcon(FIF.CARE_LEFT_SOLID)
            self.toggle_button.setToolTip("展开右侧面板")
            target_width = 0
        self.animation.setStartValue(start_width)
        self.animation.setEndValue(target_width)
        self.animation.start()

    def _on_animation_finished(self) -> None:
        if not self.is_expanded:
            self.content.setVisible(False)
