from __future__ import annotations

from PyQt5.QtGui import QIcon

from core.config import RESOURCE_ROOT


ICON_DIR = RESOURCE_ROOT / "assets" / "icons"


def brand_icon(file_name: str, fallback: QIcon) -> QIcon:
    icon = QIcon(str(ICON_DIR / file_name))
    return icon if not icon.isNull() else fallback
