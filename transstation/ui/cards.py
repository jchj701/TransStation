"""条目卡片列表：QListView + 自绘 delegate（行卡片）。

- 分批加载：先取 page_size 条，滚动到底部再追加。
- 交互：单击选中、双击默认动作、右键菜单、按住拖出。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QListView,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)

from transstation.core.mirror import ensure_thumbnail, thumb_path
from transstation.core.timefmt import rel_time
from transstation.resources.icons import svg_for
from transstation.resources.strings_zh import STR
from transstation.resources.tokens import COLORS, RADIUS
from transstation.store.db import Item

ROW_H = 76
PAD = 6

KIND_META = {
    "file": {"icon": "file", "color": COLORS["kind_file"]},
    "image": {"icon": "image", "color": COLORS["kind_image"]},
    "link": {"icon": "link", "color": COLORS["kind_link"]},
    "text": {"icon": "text", "color": COLORS["kind_text"]},
}


def _svg_pixmap(name: str, color: str, size: int, dpr: float) -> QPixmap:
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(svg_for(name, color)).render(
        p, QRect(0, 0, px.width(), px.height())
    )
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


class CardListModel(QAbstractListModel):
    """只读列表模型：批量替换、追加、局部刷新。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[Item] = []

    def reset_items(self, items: list[Item]) -> None:
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def append_items(self, items: list[Item]) -> None:
        if not items:
            return
        start = len(self.items)
        self.beginInsertRows(QModelIndex(), start, start + len(items) - 1)
        self.items.extend(items)
        self.endInsertRows()

    def replace_row(self, row: int, item: Item) -> None:
        if 0 <= row < len(self.items):
            self.items[row] = item
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.UserRole:
            return self.items[index.row()]
        return None

    def item_at(self, row: int) -> Item | None:
        return self.items[row] if 0 <= row < len(self.items) else None

    def row_of_id(self, item_id: int) -> int:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                return i
        return -1


class CardDelegate(QStyledItemDelegate):
    """行卡片绘制：缩略图/类型图标 + 标题 + 副行 + 备注 + 置顶角标。"""

    def __init__(self, view: "CardList", parent=None):
        super().__init__(view)
        self.view = view
        self._pm_cache: dict = {}

    def _pm(self, name: str, color: str, size: int) -> QPixmap:
        key = (name, color, size)
        pm = self._pm_cache.get(key)
        if pm is None:
            pm = _svg_pixmap(name, color, size, self.view.devicePixelRatioF())
            self._pm_cache[key] = pm
        return pm

    def sizeHint(self, option, index) -> QSize:
        w = option.rect.width() if option.rect.width() > 0 else 400
        return QSize(w, ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: Item | None = index.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(2, 2, -2, -2)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            bg = COLORS["surface_active"]
        elif hovered:
            bg = COLORS["surface_hover"]
        else:
            bg = COLORS["surface"]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, RADIUS["card"], RADIUS["card"])
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen_color = COLORS["accent"] if selected else COLORS["border"]
        painter.setPen(QColor(pen_color))
        painter.drawRoundedRect(rect, RADIUS["card"], RADIUS["card"])

        # 左侧视觉块
        icon_box = QRect(rect.left() + PAD, rect.top() + PAD, 56, 56)
        thumb = self._thumb(item) if item.kind == "image" else None
        if thumb is not None:
            painter.drawPixmap(
                icon_box.left() + (56 - thumb.width()) // 2,
                icon_box.top() + (56 - thumb.height()) // 2,
                thumb,
            )
        else:
            meta = KIND_META.get(item.kind, KIND_META["file"])
            name = "folder" if (item.kind == "file" and item.is_dir) else meta["icon"]
            pm = self._pm(name, meta["color"], 22)
            painter.drawPixmap(icon_box.center().x() - 11, icon_box.center().y() - 11, pm)

        # 文字区
        text_left = icon_box.right() + 10
        text_right = rect.right() - 24
        f_title = _font(self.view.font(), 13, QFont.Weight.DemiBold)
        f_sub = _font(self.view.font(), 11, QFont.Weight.Normal)
        f_note = _font(self.view.font(), 10, QFont.Weight.Normal)
        title = item.title or _no_title(item)
        painter.setFont(f_title)
        fm = QFontMetrics(f_title)
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.drawText(
            QRect(text_left, rect.top() + 6, text_right - text_left, 22),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            fm.elidedText(title, Qt.TextElideMode.ElideRight, max(text_right - text_left, 10)),
        )

        painter.setFont(f_sub)
        fm = QFontMetrics(f_sub)
        painter.setPen(QColor(COLORS["text_secondary"]))
        painter.drawText(
            QRect(text_left, rect.top() + 32, text_right - text_left, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            fm.elidedText(_sub_line(item), Qt.TextElideMode.ElideRight, max(text_right - text_left, 10)),
        )

        if item.notes:
            painter.setFont(f_note)
            fm = QFontMetrics(f_note)
            painter.setPen(QColor(COLORS["text_tertiary"]))
            painter.drawText(
                QRect(text_left, rect.top() + 52, text_right - text_left, 16),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "备注：" + fm.elidedText(item.notes, Qt.TextElideMode.ElideRight, max(text_right - text_left, 10)),
            )

        if item.pinned:
            pm = self._pm("pinfill", COLORS["warn"], 13)
            painter.drawPixmap(rect.right() - 22, rect.top() + 9, pm)
        painter.restore()

    def _thumb(self, item: Item) -> QPixmap | None:
        tp = thumb_path(item.id)
        if not tp.exists():
            ensure_thumbnail(item)
            if not tp.exists():
                return None
        pm = QPixmap(str(tp))
        if pm.isNull():
            return None
        return pm.scaled(
            56, 56,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )


def _font(base: QFont, pixel: float, weight: QFont.Weight) -> QFont:
    f = QFont(base)
    f.setPixelSize(int(pixel))
    f.setWeight(weight)
    return f


def _sub_line(item: Item) -> str:
    parts = [rel_time(item.created_at)]
    if item.kind in ("file", "image"):
        src = item.src_app or _path_tail(item.path) or _path_tail(item.image_file)
    else:
        src = item.src_app
    if src:
        parts.append(src)
    return " · ".join(p for p in parts if p)


def _path_tail(p: str) -> str:
    if not p:
        return ""
    try:
        path = Path(p)
        parent = path.parent
        if parent and parent.name:
            return f"{parent.name}/{path.name}"
        return path.name
    except Exception:
        return p


def _no_title(item: Item) -> str:
    if item.kind in ("file", "image", "link", "text"):
        return STR[f"kind_{item.kind}"]
    return ""


class CardList(QListView):
    """行卡片列表视图。"""

    activated_item = Signal(object)        # Item（双击/回车）
    context_item = Signal(object, object)  # (Item, 全局坐标)
    drag_started = Signal(object, object)  # (Item, 全局按下点)
    load_more_needed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CardList")
        self.setModel(CardListModel(self))
        self.setItemDelegate(CardDelegate(self, self))
        self.setUniformItemSizes(True)
        self.setSpacing(2)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(False)
        self.setAcceptDrops(True)
        self._press_pos: QPoint | None = None
        self._press_row = -1
        self.verticalScrollBar().valueChanged.connect(self._maybe_load_more)

    # ---------- 模型便利 ----------
    def model_items(self) -> CardListModel:
        return self.model()

    def reset_items(self, items) -> None:
        self.model_items().reset_items(items)

    def append_items(self, items) -> None:
        self.model_items().append_items(items)

    def replace_item(self, item: Item) -> None:
        row = self.model_items().row_of_id(item.id)
        if row >= 0:
            self.model_items().replace_row(row, item)

    def current_item(self) -> Item | None:
        idx = self.currentIndex()
        return self.model_items().item_at(idx.row()) if idx.isValid() else None

    # ---------- 鼠标 ----------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            idx = self.indexAt(event.position().toPoint())
            if idx.isValid():
                self.setCurrentIndex(idx)
                item = self.model_items().item_at(idx.row())
                if item is not None:
                    self.context_item.emit(
                        item, self.viewport().mapToGlobal(event.position().toPoint())
                    )
                event.accept()
                return
        elif event.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(event.position().toPoint())
            self._press_pos = event.position().toPoint()
            self._press_row = idx.row() if idx.isValid() else -1
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._press_row >= 0
            and self._press_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = (event.position().toPoint() - self._press_pos).manhattanLength()
            if delta >= QApplication.startDragDistance():
                item = self.model_items().item_at(self._press_row)
                self._press_row = -1
                if item is not None:
                    self.drag_started.emit(
                        item, self.viewport().mapToGlobal(self._press_pos)
                    )
                    event.accept()
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_row = -1
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(event.position().toPoint())
            if idx.isValid():
                item = self.model_items().item_at(idx.row())
                if item is not None:
                    self.activated_item.emit(item)
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    # ---------- 键盘 ----------
    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.current_item()
            if item is not None:
                self.activated_item.emit(item)
                event.accept()
                return
        super().keyPressEvent(event)

    # ---------- 拖放转发（由 Panel 统一处理） ----------
    def dragEnterEvent(self, event):
        event.ignore()

    def dragMoveEvent(self, event):
        event.ignore()

    def dragLeaveEvent(self, event):
        event.ignore()

    def dropEvent(self, event):
        event.ignore()

    def _maybe_load_more(self, value: int) -> None:
        sb = self.verticalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() - 60:
            self.load_more_needed.emit()
