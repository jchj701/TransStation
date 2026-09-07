"""UI 公共小件：图标按钮、筛选 chip、工具函数。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QToolButton, QWidget

from transstation.resources.style import icon
from transstation.resources.tokens import COLORS


def icon_button(
    name: str,
    tooltip: str = "",
    size: int = 16,
    color: str | None = None,
    checkable: bool = False,
    parent: QWidget | None = None,
) -> QToolButton:
    btn = QToolButton(parent)
    btn.setObjectName("IconBtn")
    btn.setIcon(icon(name, color or COLORS["text_secondary"], size))
    btn.setIconSize(QSize(size, size))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(tooltip)
    btn.setCheckable(checkable)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setFixedSize(size + 12, size + 12)
    return btn


def chip_button(text: str, parent: QWidget | None = None) -> QToolButton:
    btn = QToolButton(parent)
    btn.setObjectName("FilterChip")
    btn.setText(text)
    btn.setCheckable(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    btn.setAutoExclusive(True)
    return btn


def update_icon(btn: QToolButton, name: str, color: str, size: int = 16) -> None:
    btn.setIcon(icon(name, color, size))
