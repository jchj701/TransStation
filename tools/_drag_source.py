"""e2e 拖拽源窗口：真实 OLE 拖拽（QDrag）的提供方。

窗口固定在屏幕 (700, 150)，内容区约 400x300；按住左键拖出超过阈值即发起
真实 OLE 拖拽。payload=file 时携带本地文件（CF_HDROP）；payload=text 时携带
纯文本+HTML（模拟从编辑器/浏览器拖出文字）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDrag, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QWidget

PAYLOAD = sys.argv[1] if len(sys.argv) > 1 else "file"
SAMPLE = None
if "--sample" in sys.argv:
    SAMPLE = sys.argv[sys.argv.index("--sample") + 1]


class Source(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("e2e drag source")
        self.setGeometry(700, 150, 400, 300)
        label = QLabel("按住这里拖出（file）" if PAYLOAD == "file" else "按住这里拖出（text）", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setGeometry(0, 0, 400, 300)
        label.setStyleSheet("font-size:18px;border:2px dashed #888;")
        self._press = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._press is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() < QApplication.startDragDistance() + 4:
            return
        self._press = None
        mime = QMimeData()
        if PAYLOAD == "file" and SAMPLE:
            mime.setUrls([QUrl.fromLocalFile(SAMPLE)])
            mime.setText(SAMPLE)
        else:
            mime.setText("拖拽出的纯文本内容 e2e-text-123")
            mime.setHtml('<a href="https://example.com/">e2e 链接示例</a>')
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
        print("SOURCE_DRAG_DONE", flush=True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Source()
    w.show()
    app.exec()
