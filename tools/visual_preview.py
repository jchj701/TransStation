"""视觉预览辅助脚本（开发用）：种子数据 + 自动呼出面板，供人工/截图检查 UI。

用法：python tools/visual_preview.py [--data-dir X] [--seconds 25]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA = None


def _seed(store) -> None:
    """构造覆盖各类型/状态的示例条目。"""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtCore import Qt

    # 生成一张示例 PNG
    img_dir = DATA / "sample"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / "preview-photo.png"
    im = QImage(480, 300, QImage.Format.Format_RGB32)
    p = QPainter(im)
    p.fillRect(im.rect(), Qt.GlobalColor.darkBlue)
    p.setPen(Qt.GlobalColor.white)
    p.drawText(im.rect(), Qt.AlignmentFlag.AlignCenter, "示例图片 480x300")
    p.end()
    im.save(str(img_path), "PNG")

    txt_path = img_dir / "会议纪要.md"
    txt_path.write_text("# 会议纪要\n\n- 结论 A\n- 结论 B", encoding="utf-8")

    rows = [
        dict(kind="link", title="中转站产品需求文档", url="https://docs.example.com/transstation/prd",
             content="https://docs.example.com/transstation/prd", src_app="Chrome", pinned=True),
        dict(kind="image", title="preview-photo.png", path=str(img_path), src_app="文件资源管理器"),
        dict(kind="text", title="会议纪要", content="# 会议纪要\n\n- 结论 A\n- 结论 B",
             notes="待整理进周报", src_app="Visual Studio Code"),
        dict(kind="file", title="数据备份.zip", path=str(txt_path.parent / "数据备份.zip"),
             src_app="文件资源管理器"),
        dict(kind="link", title="https://example.com/very/long/path/that/keeps/going/and/going",
             url="https://example.com/very/long/path/that/keeps/going/and/going",
             src_app="Edge"),
        dict(kind="text", title="一段较长的示例文本内容用于观察卡片文字截断效果",
             content="一段较长示例文本\n第二行", src_app="记事本"),
        dict(kind="file", title="文件夹示例", path=str(img_dir), flags="dir", src_app="文件资源管理器"),
        dict(kind="link", title="示例链接", url="https://example.com/", src_app="微信"),
    ]
    for row in rows:
        kw = {k: v for k, v in row.items() if k in {
            "title", "content", "path", "url", "image_file", "notes", "pinned",
            "flags", "src_app", "src_window",
        }}
        store.create(row["kind"], **kw)


def main() -> int:
    import os

    global DATA
    args = [a for a in sys.argv[1:] if a != "--"]
    data_arg = None
    seconds = 25
    if "--data-dir" in args:
        data_arg = args[args.index("--data-dir") + 1]
    if "--seconds" in args:
        try:
            seconds = int(args[args.index("--seconds") + 1])
        except (IndexError, ValueError):
            pass

    os.environ.setdefault("TRANS_PREVIEW", "1")
    from PySide6.QtGui import QGuiApplication, QCursor
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("TransStationPreview")
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    from transstation.resources.style import build_qss, force_light_palette, setup_application_font

    if data_arg:
        paths.override_data_dir(Path(data_arg))
    paths.ensure_dirs()
    global DATA
    DATA = paths.sub_dirs()["root"]

    from transstation.app import App
    from transstation.store.db import Store

    # 手动构造（跳过托盘/热键/单实例）
    from transstation.store.settings import Settings

    dirs = paths.sub_dirs()
    settings = Settings(dirs["root"] / "settings.json")
    store = Store(dirs["db"] / "preview.db")
    ctl = App(app, data_dir_override=data_arg)  # 复用日志等
    _seed(store)

    setup_application_font()
    force_light_palette()
    app.setStyleSheet(build_qss())

    from transstation.ui.panel import Panel

    panel = Panel(store, settings, hotkey_text="Ctrl+Alt+T")
    # 预览不拦截任何全局操作
    panel.reload()

    screen = QGuiApplication.primaryScreen()
    geo = screen.availableGeometry()
    QCursor.setPos(geo.left() + geo.width() // 2, geo.top() + geo.height() // 3)
    panel.pinned = False
    panel._place_near_cursor()

    # 展示两阶段：有内容 → 4 秒后切换搜索“没有结果”空态 → 清库空态
    def stage2():
        from PySide6.QtWidgets import QLineEdit

        _shot("2_search_empty")
        panel._search.setText("不存在的关键词xyz")
        panel.reload()
        QTimer.singleShot(400, lambda: _shot("3_filtered"))

    def stage3():
        panel._search.clear()
        panel.reload()
        store.soft_delete([i.id for i in store.list_items()])
        panel.notify_list_changed()
        QTimer.singleShot(400, lambda: _shot("4_all_deleted"))

    def stage4():
        # 关闭预览
        app.exit(0)

    import tempfile
    from PySide6.QtCore import QTimer

    shot_dir = Path(tempfile.gettempdir()) / "trans_preview"
    shot_dir.mkdir(exist_ok=True)

    def _shot(tag: str) -> None:
        panel.grab().save(str(shot_dir / f"{tag}.png"))
        print(f"captured {tag}", flush=True)

    panel.show()
    panel.raise_()
    QTimer.singleShot(900, lambda: _shot("1_populated"))
    QTimer.singleShot(seconds * 1000 // 3, stage2)
    QTimer.singleShot(seconds * 1000 // 3 * 2, stage3)
    QTimer.singleShot(seconds * 1000, stage4)
    print("PREVIEW_RUNNING", flush=True)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
