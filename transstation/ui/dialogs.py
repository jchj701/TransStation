"""通用小对话框：文本内容查看/编辑、备注编辑、确认框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from transstation.resources.strings_zh import STR


def _buttons(parent: QDialog, primary_text: str = "确定", with_cancel: bool = True) -> QDialogButtonBox:
    box = QDialogButtonBox(parent)
    ok = box.addButton(primary_text, QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setObjectName("PrimaryBtn")
    if with_cancel:
        box.addButton(STR["cancel"], QDialogButtonBox.ButtonRole.RejectRole)
    box.accepted.connect(parent.accept)
    box.rejected.connect(parent.reject)
    return box


class ContentDialog(QDialog):
    """文本内容查看/编辑（保存后回调）。"""

    def __init__(self, title: str, content: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(STR["text_content_title"])
        self.setMinimumSize(420, 340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        head = QLabel(title)
        head.setStyleSheet("font-weight:600;")
        head.setWordWrap(True)
        lay.addWidget(head)
        self._edit = QPlainTextEdit()
        self._edit.setPlainText(content)
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self._edit, 1)
        self._save = QPushButton(STR["text_edit_save"])
        self._save.setObjectName("PrimaryBtn")
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.clicked.connect(self.accept)
        row = QDialogButtonBox(self)
        row.addButton(self._save, QDialogButtonBox.ButtonRole.AcceptRole)
        row.addButton(STR["cancel"], QDialogButtonBox.ButtonRole.RejectRole)
        row.rejected.connect(self.reject)
        lay.addWidget(row)
        self._edit.setFocus()

    def result_content(self) -> str:
        return self._edit.toPlainText()


class NotesDialog(QDialog):
    """编辑备注。"""

    def __init__(self, title: str, notes: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(STR["notes_title"])
        self.setMinimumSize(400, 220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        head = QLabel(title)
        head.setStyleSheet("font-weight:600;")
        head.setWordWrap(True)
        lay.addWidget(head)
        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText(STR["notes_placeholder"])
        self._edit.setPlainText(notes)
        lay.addWidget(self._edit, 1)
        lay.addWidget(_buttons(self, STR["ok"]))
        self._edit.setFocus()

    def result_notes(self) -> str:
        return self._edit.toPlainText().strip()


class ConfirmDialog(QDialog):
    """带说明文字的确认框。"""

    def __init__(self, text: str, ok_text: str = "确定", danger: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("中转站")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 14)
        lay.setSpacing(16)
        msg = QLabel(text)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        box = QDialogButtonBox(self)
        ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        if danger:
            ok.setObjectName("DangerBtn")
        else:
            ok.setObjectName("PrimaryBtn")
        box.addButton(STR["cancel"], QDialogButtonBox.ButtonRole.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.setMinimumWidth(360)
