"""回收站窗口：恢复 / 彻底删除 / 清空。"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from transstation.core.timefmt import rel_time
from transstation.resources.strings_zh import STR
from transstation.store.db import Item, Store
from transstation.store.settings import Settings


class RecycleDialog(QDialog):
    """回收站：软删除条目保留 30 天，可恢复或彻底删除。"""

    def __init__(self, store: Store, settings: Settings, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(STR["recycle_title"])
        self.resize(560, 400)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        tip = QLabel(STR["recycle_keep_days"])
        tip.setStyleSheet("color:#8A93A2;font-size:12px;")
        lay.addWidget(tip)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lay.addWidget(self._list, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        restore = QPushButton(STR["recycle_restore"])
        restore.setObjectName("PrimaryBtn")
        purge = QPushButton(STR["recycle_purge"])
        close = QPushButton(STR["close"])
        clear_all = QPushButton(STR["recycle_purge_all"])
        clear_all.setObjectName("DangerBtn")
        restore.clicked.connect(self._restore)
        purge.clicked.connect(self._purge)
        clear_all.clicked.connect(self._purge_all)
        close.clicked.connect(self.accept)
        btns.addWidget(clear_all)
        btns.addWidget(purge)
        btns.addWidget(restore)
        btns.addWidget(close)
        lay.addLayout(btns)
        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        deleted = self.store.list_deleted()
        if not deleted:
            empty = QListWidgetItem(STR["recycle_empty"])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(empty)
            return
        for item in deleted:
            name = item.title or STR[f"kind_{item.kind}"]
            self._list.addItem(
                QListWidgetItem(f"[{STR[f'kind_{item.kind}']}] {name}  ·  {rel_time(item.deleted_at)}")
            )
        self._items = deleted

    def _selected_items(self) -> list[Item]:
        if not hasattr(self, "_items"):
            return []
        rows = {idx.row() for idx in self._list.selectedIndexes()}
        return [it for i, it in enumerate(self._items) if i in rows]

    def _restore(self) -> None:
        items = self._selected_items()
        if not items:
            return
        self.store.restore([it.id for it in items])
        self._reload()

    def _purge(self) -> None:
        items = self._selected_items()
        if not items:
            return
        from transstation.core.mirror import cleanup_item_files

        purged = self.store.hard_delete([it.id for it in items])
        for it in purged:
            cleanup_item_files(it)
        self._reload()

    def _purge_all(self) -> None:
        from transstation.core.mirror import cleanup_item_files

        while True:
            batch = self.store.list_deleted()
            if not batch:
                break
            for it in self.store.hard_delete([x.id for x in batch]):
                cleanup_item_files(it)
        self._reload()
