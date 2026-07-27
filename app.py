from __future__ import annotations

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog
from qfluentwidgets import Theme, setTheme, setThemeColor

from core.config import APP_ROOT, LICENSE_REQUIRED, RESOURCE_ROOT, RUNTIME_DIR, ensure_dirs
from core.crash_guard import install_crash_guard
from core.license_service import LicenseService
from core.toolchain import resolve_toolchain
from ui.license_dialog import LicenseDialog
from ui.main_window import MainWindow


if sys.platform == "win32":
    plugin_path = os.path.join(sys.prefix, "Lib", "site-packages", "PyQt5", "Qt5", "plugins")
    if os.path.isdir(plugin_path):
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", plugin_path)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv

    if "--self-test" in argv:
        ensure_dirs()
        toolchain = resolve_toolchain()
        print("SELF_TEST_OK")
        print(APP_ROOT)
        print(RESOURCE_ROOT)
        print(toolchain.bbdown)
        print(toolchain.ffmpeg)
        print(toolchain.aria2c)
        return 0

    ensure_dirs()
    install_crash_guard(RUNTIME_DIR)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(argv)
    setTheme(Theme.DARK)
    setThemeColor("#4cc2ff")

    if LICENSE_REQUIRED:
        license_service = LicenseService()
        license_result = license_service.verify(force=True)
        if not license_result.ok:
            dialog = LicenseDialog(license_service)
            if dialog.exec() != QDialog.Accepted:
                return 0

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
