"""新手引导覆盖层：首次呼出时展示三步说明。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from transstation.resources.strings_zh import STR


class OnboardingOverlay(QFrame):
    """铺在面板内容之上的半透明引导层；点“开始使用”后触发 on_done。"""

    def __init__(self, parent: QWidget, on_done=None):
        super().__init__(parent)
        self._on_done = on_done
        self.setObjectName("OnboardOverlay")
        self.setStyleSheet(
            "QFrame#OnboardOverlay{background:rgba(255,255,255,0.96);border:1px solid #E4E7ED;"
            "border-radius:12px;}"
            "QLabel{background:transparent;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 24)
        lay.setSpacing(12)
        title = QLabel(STR["onboard_title"])
        title.setStyleSheet("font-size:17px;font-weight:700;color:#1F2329;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)
        for line in (
            STR["onboard_1"], STR["onboard_2"], STR["onboard_3"], STR["onboard_more"]
        ):
            lbl = QLabel(line)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size:13px;color:#5A6270;")
            lay.addWidget(lbl)
        lay.addSpacing(8)
        btn = QPushButton(STR["onboard_start"])
        btn.setObjectName("PrimaryBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumWidth(140)
        btn.clicked.connect(self.finish)
        box = QVBoxLayout()
        box.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addLayout(box)

    def finish(self) -> None:
        self.hide()
        if self._on_done:
            cb, self._on_done = self._on_done, None
            cb()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
