from __future__ import annotations

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme, setThemeColor

from core.config import APP_ROOT, RESOURCE_ROOT, ensure_dirs
from core.toolchain import resolve_toolchain
from ui.main_window import MainWindow


if sys.platform == "win32":
    plugin_path = os.path.join(sys.prefix, "Lib", "site-packages", "PyQt5", "Qt5", "plugins")
    if os.path.isdir(plugin_path):
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", plugin_path)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    trace_path = APP_ROOT / "startup_trace.log"

    def trace(message: str) -> None:
        try:
            ensure_dirs()
            with trace_path.open("a", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except Exception:
            pass

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

    trace("main:start")
    ensure_dirs()
    trace("main:dirs_ready")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    trace("main:qt_attrs_set")
    app = QApplication(argv)
    trace("main:qapp_created")
    setTheme(Theme.DARK)
    setThemeColor("#4cc2ff")
    trace("main:theme_set")
    window = MainWindow()
    trace("main:window_created")
    window.show()
    trace("main:window_shown")
    result = app.exec()
    trace(f"main:app_exec_returned:{result}")
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
