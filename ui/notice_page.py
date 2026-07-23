from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, FluentIcon as FIF, HyperlinkButton, TitleLabel

from .widgets import CardFrame


UPDATE_URL = "https://rcnyou54a8x8.feishu.cn/docx/RjwndtvZXoZ5Orx2LiRcfISfnMf?from=from_copylink"


class NoticePage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("usageNotice")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)
        root.addWidget(TitleLabel("使用须知", self))

        update_card = CardFrame(self)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(18, 18, 18, 18)
        update_layout.setSpacing(10)
        update_layout.addWidget(BodyLabel("更新链接", update_card))

        url_label = CaptionLabel(UPDATE_URL, update_card)
        url_label.setWordWrap(True)
        url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        update_layout.addWidget(url_label)

        action_row = QHBoxLayout()
        open_link_btn = HyperlinkButton(FIF.LINK, UPDATE_URL, "打开更新链接", update_card)
        action_row.addWidget(open_link_btn)
        action_row.addStretch(1)
        update_layout.addLayout(action_row)

        root.addWidget(update_card)
        root.addStretch(1)
