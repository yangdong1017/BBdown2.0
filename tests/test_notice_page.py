from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.notice_page import (
    FEISHU_ICON_PATH,
    UPDATE_URL,
    WECHAT_ID,
    WECHAT_ICON_PATH,
    WECHAT_OFFICIAL_QR_PATH,
    WECHAT_PAY_QR_PATH,
    NoticePage,
)


class NoticePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qr_assets_are_bundled_and_loaded(self) -> None:
        self.assertTrue(FEISHU_ICON_PATH.is_file())
        self.assertTrue(WECHAT_ICON_PATH.is_file())
        self.assertTrue(WECHAT_PAY_QR_PATH.is_file())
        self.assertTrue(WECHAT_OFFICIAL_QR_PATH.is_file())

        page = NoticePage()
        self.assertIsNotNone(page.update_brand_icon.pixmap())
        self.assertIsNotNone(page.contact_brand_icon.pixmap())
        self.assertTrue(page.pay_card.qr_button.pixmap_loaded)
        self.assertTrue(page.official_card.qr_button.pixmap_loaded)
        page.deleteLater()

    def test_contact_details_are_visible_and_copyable(self) -> None:
        page = NoticePage()
        self.assertEqual(page.wechat_id_label.text(), WECHAT_ID)

        with patch("ui.notice_page.QApplication.clipboard") as clipboard:
            page.copy_wechat_btn.click()
            clipboard.return_value.setText.assert_called_once_with(WECHAT_ID)

        self.assertEqual(page.copy_wechat_btn.text(), "已复制")
        page._reset_copy_button()
        self.assertEqual(page.copy_wechat_btn.text(), "复制微信号")
        page.deleteLater()

    def test_update_link_uses_the_system_browser(self) -> None:
        page = NoticePage()

        with patch("ui.notice_page.QDesktopServices.openUrl", return_value=True) as open_url:
            page.open_link_btn.click()

        self.assertEqual(open_url.call_args.args[0].toString(), UPDATE_URL)
        page.deleteLater()

    def test_clicking_qr_opens_large_preview(self) -> None:
        page = NoticePage()

        with patch("ui.notice_page.QrPreviewDialog.exec", return_value=0) as preview:
            page.pay_card.qr_button.click()

        preview.assert_called_once_with()
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
