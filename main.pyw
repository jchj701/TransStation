"""中转站 TransStation —— 入口（.pyw 无控制台）。

用法：
    python main.pyw                 # 正常运行（驻留托盘）
    python main.pyw --smoke         # 自动化自检（offscreen，无窗口）
    python main.pyw --data-dir X    # 使用 X 作为数据目录
"""
from __future__ import annotations

import os
import sys


def _main() -> int:
    smoke = "--smoke" in sys.argv or bool(os.environ.get("TRANS_SMOKE"))
    data_dir = None
    if "--data-dir" in sys.argv:
        try:
            data_dir = sys.argv[sys.argv.index("--data-dir") + 1]
        except IndexError:
            data_dir = None
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ["TRANS_SMOKE"] = "1"

    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("TransStation")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("TransStation")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(_app_icon())

    from transstation.app import App
    from transstation.resources.style import build_qss, force_light_palette, setup_application_font

    setup_application_font()
    force_light_palette()   # 深色系统主题下强制浅色（否则未 QSS 覆盖处黑底黑字）
    app.setStyleSheet(build_qss())

    ctl = App(app, data_dir_override=data_dir)
    ctl.start()
    if not ctl._running:
        # 第二实例：唤醒已有实例后直接退出
        ctl.shutdown()
        return 0
    if smoke:
        # 冒烟流程自带退出
        return app.exec()
    app.aboutToQuit.connect(ctl.shutdown)
    return app.exec()


def _app_icon():
    from PySide6.QtGui import QIcon

    from transstation.resources.style import icon
    from transstation.resources.tokens import COLORS

    return icon("logo", COLORS["accent"], 16)


if __name__ == "__main__":
    sys.exit(_main())
