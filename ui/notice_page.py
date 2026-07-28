from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt5.QtCore import QSize, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon as FIF,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    TitleLabel,
)

from core.config import RESOURCE_ROOT
from .widgets import CardFrame


UPDATE_URL = "https://rcnyou54a8x8.feishu.cn/docx/RjwndtvZXoZ5Orx2LiRcfISfnMf?from=from_copylink"
WECHAT_ID = "duya9888"
NOTICE_ASSET_DIR = RESOURCE_ROOT / "assets" / "notice"
FEISHU_ICON_PATH = NOTICE_ASSET_DIR / "feishu.png"
WECHAT_ICON_PATH = NOTICE_ASSET_DIR / "wechat.ico"
WECHAT_PAY_QR_PATH = NOTICE_ASSET_DIR / "wechat-pay-qr.png"
WECHAT_OFFICIAL_QR_PATH = NOTICE_ASSET_DIR / "wechat-official-qr.png"


class QrImageButton(QPushButton):
    """Square QR preview that keeps its quiet zone and opens at full size."""

    def __init__(self, image_path: Path, accessible_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image_path = image_path
        self.setObjectName("qrImageButton")
        self.setAccessibleName(accessible_name)
        self.setToolTip("点击放大")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(176, 176)
        self.setIconSize(QSize(152, 152))
        self.setStyleSheet(
            """
            QPushButton#qrImageButton {
                background: #ffffff;
                border: 10px solid #ffffff;
                border-radius: 12px;
                padding: 0;
            }
            QPushButton#qrImageButton:hover {
                border-color: #e7f8ef;
                background: #e7f8ef;
            }
            QPushButton#qrImageButton:pressed {
                border-color: #d9f2e4;
                background: #d9f2e4;
            }
            """
        )

        pixmap = QPixmap(str(image_path))
        self.pixmap_loaded = not pixmap.isNull()
        if self.pixmap_loaded:
            self.setIcon(QIcon(pixmap))
        else:
            self.setText("二维码\n加载失败")
            self.setStyleSheet(self.styleSheet() + "QPushButton#qrImageButton { color: #333333; }")


class QrPreviewDialog(QDialog):
    def __init__(self, title: str, image_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(430, 490)
        self.setStyleSheet(
            """
            QDialog {
                background: #18191c;
                color: #f3f5f7;
            }
            QLabel#qrPreviewImage {
                background: #ffffff;
                border: 12px solid #ffffff;
                border-radius: 13px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        heading = BodyLabel(title, self)
        heading.setStyleSheet("color: #f3f5f7; font-size: 16px; font-weight: 600;")
        layout.addWidget(heading)

        image_label = QLabel(self)
        image_label.setObjectName("qrPreviewImage")
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setFixedSize(362, 362)
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            image_label.setText("二维码加载失败")
            image_label.setStyleSheet(image_label.styleSheet() + "color: #333333;")
        else:
            image_label.setPixmap(pixmap.scaled(338, 338, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(image_label, 0, Qt.AlignHCenter)

        footer_row = QHBoxLayout()
        footer_row.addWidget(CaptionLabel("请使用微信扫描二维码", self))
        footer_row.addStretch(1)
        close_button = PushButton("关闭", self)
        close_button.setFixedWidth(76)
        close_button.clicked.connect(self.accept)
        footer_row.addWidget(close_button)
        layout.addLayout(footer_row)


class SupportCard(CardFrame):
    def __init__(
        self,
        *,
        badge: str,
        title: str,
        description: str,
        footnote: str,
        image_path: Path,
        open_preview: Callable[[str, Path], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            self.styleSheet()
            + """
            QLabel#wechatBadge {
                color: #50db92;
                background: rgba(7, 193, 96, 0.12);
                border: 1px solid rgba(7, 193, 96, 0.18);
                border-radius: 10px;
                padding: 3px 8px;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        self.qr_button = QrImageButton(image_path, f"{title}二维码", self)
        self.qr_button.clicked.connect(lambda: open_preview(title, image_path))
        layout.addWidget(self.qr_button, 0, Qt.AlignVCenter)

        copy_layout = QVBoxLayout()
        copy_layout.setSpacing(7)

        badge_label = CaptionLabel(f"●  {badge}", self)
        badge_label.setObjectName("wechatBadge")
        badge_label.setFixedHeight(25)
        badge_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        copy_layout.addWidget(badge_label, 0, Qt.AlignLeft)

        title_label = BodyLabel(title, self)
        title_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #f3f5f7;")
        title_label.setWordWrap(True)
        copy_layout.addWidget(title_label)

        description_label = CaptionLabel(description, self)
        description_label.setStyleSheet("color: #a7abb1; font-size: 12px;")
        description_label.setWordWrap(True)
        copy_layout.addWidget(description_label)
        copy_layout.addStretch(1)

        footnote_label = CaptionLabel(footnote, self)
        footnote_label.setStyleSheet("color: #747982; font-size: 10px;")
        footnote_label.setWordWrap(True)
        copy_layout.addWidget(footnote_label)

        layout.addLayout(copy_layout, 1)


class NoticePage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("usageNotice")
        self.copy_reset_timer = QTimer(self)
        self.copy_reset_timer.setSingleShot(True)
        self.copy_reset_timer.timeout.connect(self._reset_copy_button)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        root.addWidget(TitleLabel("使用须知", self))
        intro_label = CaptionLabel("查看软件更新、支持作者或关注公众号。", self)
        intro_label.setStyleSheet("color: #a7abb1;")
        root.addWidget(intro_label)
        root.addSpacing(4)

        update_card = CardFrame(self)
        update_card.setMinimumHeight(92)
        update_layout = QHBoxLayout(update_card)
        update_layout.setContentsMargins(18, 16, 18, 16)
        update_layout.setSpacing(15)

        self.update_brand_icon = QLabel(update_card)
        self.update_brand_icon.setAccessibleName("飞书")
        self.update_brand_icon.setAlignment(Qt.AlignCenter)
        self.update_brand_icon.setFixedSize(42, 42)
        feishu_pixmap = QIcon(str(FEISHU_ICON_PATH)).pixmap(32, 32)
        if feishu_pixmap.isNull():
            self.update_brand_icon.setText("飞书")
        else:
            self.update_brand_icon.setPixmap(feishu_pixmap)
        self.update_brand_icon.setStyleSheet(
            """
            QLabel {
                color: #a7abb1;
                background: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                font-size: 10px;
            }
            """
        )
        update_layout.addWidget(self.update_brand_icon)

        update_copy = QVBoxLayout()
        update_copy.setSpacing(5)
        update_copy.addWidget(BodyLabel("更新链接", update_card))
        self.url_label = CaptionLabel(UPDATE_URL, update_card)
        self.url_label.setStyleSheet("color: #a7abb1;")
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.url_label.setWordWrap(True)
        update_copy.addWidget(self.url_label)
        update_layout.addLayout(update_copy, 1)

        self.open_link_btn = PrimaryPushButton("打开更新链接", update_card)
        self.open_link_btn.setIcon(FIF.LINK)
        self.open_link_btn.clicked.connect(self._open_update_link)
        update_layout.addWidget(self.open_link_btn, 0, Qt.AlignVCenter)
        root.addWidget(update_card)

        root.addSpacing(6)
        section_row = QHBoxLayout()
        section_copy = QVBoxLayout()
        section_copy.setSpacing(2)
        section_title = BodyLabel("支持与关注", self)
        section_title.setStyleSheet("color: #f3f5f7; font-size: 17px; font-weight: 600;")
        section_copy.addWidget(section_title)
        section_copy.addWidget(CaptionLabel("使用微信扫描下方二维码", self))
        section_row.addLayout(section_copy)
        section_row.addStretch(1)
        zoom_tip = CaptionLabel("⌕  点击二维码可放大", self)
        zoom_tip.setStyleSheet("color: #747982;")
        section_row.addWidget(zoom_tip, 0, Qt.AlignBottom)
        root.addLayout(section_row)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.pay_card = SupportCard(
            badge="微信支付",
            title="支持作者",
            description="如果软件对你有帮助，欢迎请作者喝杯咖啡。",
            footnote="♡  自愿支持 · 不影响软件功能",
            image_path=WECHAT_PAY_QR_PATH,
            open_preview=self._show_qr_preview,
            parent=self,
        )
        self.official_card = SupportCard(
            badge="微信公众号",
            title="林清AI创业笔记",
            description="关注后获取 AI 工具、实战经验和软件更新消息。",
            footnote="⌕  微信搜一搜：林清AI创业笔记",
            image_path=WECHAT_OFFICIAL_QR_PATH,
            open_preview=self._show_qr_preview,
            parent=self,
        )
        cards_row.addWidget(self.pay_card, 1)
        cards_row.addWidget(self.official_card, 1)
        root.addLayout(cards_row)

        root.addSpacing(4)
        contact_card = CardFrame(self)
        contact_card.setMinimumHeight(64)
        contact_layout = QHBoxLayout(contact_card)
        contact_layout.setContentsMargins(16, 10, 16, 10)
        contact_layout.setSpacing(13)

        self.contact_brand_icon = QLabel(contact_card)
        self.contact_brand_icon.setAccessibleName("微信")
        self.contact_brand_icon.setAlignment(Qt.AlignCenter)
        self.contact_brand_icon.setFixedSize(42, 42)
        wechat_pixmap = QIcon(str(WECHAT_ICON_PATH)).pixmap(27, 27)
        if wechat_pixmap.isNull():
            self.contact_brand_icon.setText("微信")
        else:
            self.contact_brand_icon.setPixmap(wechat_pixmap)
        self.contact_brand_icon.setStyleSheet(
            """
            QLabel {
                color: #50db92;
                background: rgba(7, 193, 96, 0.12);
                border: 1px solid rgba(7, 193, 96, 0.18);
                border-radius: 10px;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )
        contact_layout.addWidget(self.contact_brand_icon)

        contact_copy = QVBoxLayout()
        contact_copy.setSpacing(3)
        contact_copy.addWidget(BodyLabel("联系作者", contact_card))
        contact_caption = CaptionLabel("遇到问题或希望交流，可添加微信", contact_card)
        contact_caption.setStyleSheet("color: #747982;")
        contact_copy.addWidget(contact_caption)
        contact_layout.addLayout(contact_copy)
        contact_layout.addStretch(1)

        self.wechat_id_label = QLabel(WECHAT_ID, contact_card)
        self.wechat_id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.wechat_id_label.setStyleSheet(
            """
            QLabel {
                color: #eef1f3;
                background: rgba(0, 0, 0, 0.20);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 7px;
                padding: 6px 11px;
                font-family: Consolas;
                font-size: 13px;
                font-weight: 600;
            }
            """
        )
        contact_layout.addWidget(self.wechat_id_label)

        self.copy_wechat_btn = PushButton("复制微信号", contact_card)
        self.copy_wechat_btn.clicked.connect(self._copy_wechat_id)
        contact_layout.addWidget(self.copy_wechat_btn)
        root.addWidget(contact_card)
        root.addStretch(1)

    def _open_update_link(self) -> None:
        if QDesktopServices.openUrl(QUrl(UPDATE_URL)):
            return
        MessageBox("提示", "无法打开链接，请检查系统默认浏览器设置。", self.window()).exec()

    def _show_qr_preview(self, title: str, image_path: Path) -> None:
        QrPreviewDialog(title, image_path, self.window()).exec()

    def _copy_wechat_id(self) -> None:
        QApplication.clipboard().setText(WECHAT_ID)
        self.copy_wechat_btn.setText("已复制")
        self.copy_reset_timer.start(1600)

    def _reset_copy_button(self) -> None:
        self.copy_wechat_btn.setText("复制微信号")
