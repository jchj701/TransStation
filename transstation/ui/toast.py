"""面板内 Toast：存入/删除反馈 + 撤销按钮。"""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from transstation.resources.strings_zh import STR


class ToastBar(QWidget):
    """显示在面板底部的临时提示条（淡入淡出，超时自动消失）。"""

    undo_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._duration = 3200
        self._anim: QPropertyAnimation | None = None
        self._effect: QGraphicsOpacityEffect | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_animated)

        self._bar = QFrame(self)
        self._bar.setObjectName("ToastBar")
        lay = QHBoxLayout(self._bar)
        lay.setContentsMargins(14, 7, 8, 7)
        lay.setSpacing(10)
        self._label = QLabel("")
        self._label.setObjectName("ToastText")
        self._undo = QPushButton(STR["toast_undo"])
        self._undo.setObjectName("ToastBtn")
        self._undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._undo.clicked.connect(self.undo_requested.emit)
        lay.addWidget(self._label, 1)
        lay.addWidget(self._undo)
        self._undo.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        outer.addWidget(self._bar)
        self.hide()

    def show_message(
        self,
        text: str,
        *,
        with_undo: bool = False,
        duration: int | None = None,
    ) -> None:
        if duration is not None:
            self._duration = max(800, duration)
        self._label.setText(text)
        self._undo.setVisible(with_undo)
        self._timer.stop()
        self._timer.start(self._duration)
        if not self.isVisible():
            self.show()
            self.raise_()
            self._fade(1.0, from_value=0.0)
        else:
            self._fade(1.0)

    def hide_animated(self) -> None:
        self._timer.stop()
        self._fade(0.0, on_finish=self.hide)

    def cancel(self) -> None:
        self._timer.stop()
        self._anim = None
        self.hide()

    def _fade(self, target: float, from_value: float | None = None, on_finish=None) -> None:
        if self._anim and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        if self._effect is None:
            self._effect = QGraphicsOpacityEffect(self)
            self._effect.setOpacity(1.0)
            self.setGraphicsEffect(self._effect)
        if from_value is not None:
            self._effect.setOpacity(from_value)
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(160)
        anim.setStartValue(self._effect.opacity())
        anim.setEndValue(target)
        if on_finish:
            anim.finished.connect(on_finish)
        self._anim = anim
        anim.start()
