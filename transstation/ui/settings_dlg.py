"""设置对话框（M1 子集）。

分组：呼出与窗口 / 记录与隐私 / 数据。
通过注入的 app_ops 与应用交互：
  apply(values: dict) -> str | None     # 返回错误信息则中止
  backup_now() -> str | None            # 错误信息或 None
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from transstation import paths
from transstation.core.hotkey import sequence_to_canonical
from transstation.resources.strings_zh import STR
from transstation.store.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, app_ops, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings
        self._ops = app_ops
        self.setWindowTitle(STR["settings_title"])
        self.setMinimumSize(520, 560)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)
        lay.addWidget(self._build_summon_group())
        lay.addWidget(self._build_record_group())
        lay.addWidget(self._build_data_group())
        lay.addStretch(1)

        btns = QDialogButtonBox(self)
        ok = btns.addButton(STR["ok"], QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("PrimaryBtn")
        btns.addButton(STR["cancel"], QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    # ---------- 分组 ----------
    def _build_summon_group(self) -> QGroupBox:
        g = QGroupBox(STR["settings_grp_summon"])
        form = QVBoxLayout(g)
        form.setSpacing(6)

        row1 = QHBoxLayout()
        self._hotkey_edit = QKeySequenceEdit()
        self._hotkey_edit.setMaximumWidth(180)
        seq = QKeySequence(self._settings.get("hotkey"))
        self._hotkey_edit.setKeySequence(seq)
        hint = QLabel(STR["settings_hotkey_capture_hint"])
        hint.setStyleSheet("color:#8A93A2;font-size:11px;")
        row1.addWidget(QLabel(STR["settings_hotkey"]))
        row1.addWidget(self._hotkey_edit)
        row1.addWidget(hint, 1)
        form.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(STR["settings_offset_x"]))
        self._off_x = self._spin(0, 400, self._settings.get("popup_offset_x"))
        row2.addWidget(self._off_x)
        row2.addSpacing(16)
        row2.addWidget(QLabel(STR["settings_offset_y"]))
        self._off_y = self._spin(0, 400, self._settings.get("popup_offset_y"))
        row2.addWidget(self._off_y)
        row2.addStretch(1)
        form.addLayout(row2)

        self._auto_hide = QCheckBox(STR["settings_auto_hide"])
        self._auto_hide.setChecked(bool(self._settings.get("auto_hide")))
        form.addWidget(self._auto_hide)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel(STR["settings_auto_hide_delay"]))
        self._hide_delay = self._spin(200, 8000, int(self._settings.get("auto_hide_delay_ms")), step=100)
        self._hide_delay.setSuffix(" ms")
        row3.addWidget(self._hide_delay)
        row3.addStretch(1)
        form.addLayout(row3)

        self._pin_default = QCheckBox(STR["settings_pin_default"])
        self._pin_default.setChecked(bool(self._settings.get("pin_default")))
        form.addWidget(self._pin_default)
        self._remember = QCheckBox(STR["settings_remember_geom"])
        self._remember.setChecked(bool(self._settings.get("remember_geometry")))
        form.addWidget(self._remember)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel(STR["settings_panel_w"]))
        self._p_w = self._spin(320, 1200, int(self._settings.get("panel_width")), step=10)
        row4.addWidget(self._p_w)
        row4.addSpacing(16)
        row4.addWidget(QLabel(STR["settings_panel_h"]))
        self._p_h = self._spin(360, 1400, int(self._settings.get("panel_height")), step=10)
        row4.addWidget(self._p_h)
        row4.addStretch(1)
        form.addLayout(row4)

        self._send_paste = QCheckBox(STR["settings_send_paste"])
        self._send_paste.setChecked(bool(self._settings.get("send_auto_paste")))
        form.addWidget(self._send_paste)
        return g

    def _build_record_group(self) -> QGroupBox:
        g = QGroupBox(STR["settings_grp_record"])
        lay = QVBoxLayout(g)
        lay.setSpacing(6)
        self._text_mirror = QCheckBox(STR["settings_text_mirror"])
        self._text_mirror.setChecked(bool(self._settings.get("text_mirror")))
        lay.addWidget(self._text_mirror)

        lay.addWidget(QLabel(STR["settings_ignore_list"]))
        self._ignore_list = QListWidget()
        self._ignore_list.setMaximumHeight(110)
        for pat in self._settings.get("ignore_apps") or []:
            self._ignore_list.addItem(str(pat))
        lay.addWidget(self._ignore_list)
        row = QHBoxLayout()
        self._ignore_input = QLineEdit()
        self._ignore_input.setPlaceholderText(STR["settings_ignore_hint"])
        self._ignore_input.returnPressed.connect(self._add_ignore)
        add_btn = QPushButton(STR["settings_ignore_add"])
        del_btn = QPushButton(STR["settings_ignore_del"])
        add_btn.clicked.connect(self._add_ignore)
        del_btn.clicked.connect(self._del_ignore)
        row.addWidget(self._ignore_input, 1)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        lay.addLayout(row)
        return g

    def _build_data_group(self) -> QGroupBox:
        g = QGroupBox(STR["settings_grp_data"])
        lay = QVBoxLayout(g)
        lay.setSpacing(6)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(STR["settings_data_dir"]))
        self._data_dir_label = QLabel(str(paths.data_dir()))
        self._data_dir_label.setStyleSheet("color:#5A6270;")
        self._data_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row1.addWidget(self._data_dir_label, 1)
        change_btn = QPushButton(STR["settings_data_dir_change"])
        change_btn.clicked.connect(self._choose_data_dir)
        row1.addWidget(change_btn)
        lay.addLayout(row1)
        note = QLabel(STR["settings_data_dir_move_note"])
        note.setStyleSheet("color:#8A93A2;font-size:11px;")
        note.setWordWrap(True)
        lay.addWidget(note)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(STR["settings_backup_keep"]))
        self._backup_keep = self._spin(1, 60, int(self._settings.get("backup_keep")))
        row2.addWidget(self._backup_keep)
        row2.addSpacing(16)
        now_btn = QPushButton(STR["settings_backup_now"])
        now_btn.clicked.connect(self._backup_now)
        row2.addWidget(now_btn)
        row2.addStretch(1)
        lay.addLayout(row2)
        return g

    # ---------- 帮助 ----------
    @staticmethod
    def _spin(lo: int, hi: int, value, step: int = 1) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.setSingleStep(step)
        return s

    def _add_ignore(self) -> None:
        text = self._ignore_input.text().strip()
        if text and text not in [self._ignore_list.item(i).text() for i in range(self._ignore_list.count())]:
            self._ignore_list.addItem(text)
        self._ignore_input.clear()

    def _del_ignore(self) -> None:
        for item in self._ignore_list.selectedItems():
            self._ignore_list.takeItem(self._ignore_list.row(item))

    def _choose_data_dir(self) -> None:
        start = str(paths.data_dir())
        chosen = QFileDialog.getExistingDirectory(self, STR["settings_data_dir_change"], start)
        if chosen:
            self._data_dir_label.setText(chosen)

    def _backup_now(self) -> None:
        err = self._ops.backup_now()
        if err:
            self._err(err)

    # ---------- 确认 ----------
    def _gather(self) -> dict:
        seq = sequence_to_canonical(self._hotkey_edit.keySequence())
        ignore = [self._ignore_list.item(i).text().strip()
                  for i in range(self._ignore_list.count()) if self._ignore_list.item(i).text().strip()]
        chosen_dir = self._data_dir_label.text().strip()
        return {
            "hotkey": seq,
            "popup_offset_x": self._off_x.value(),
            "popup_offset_y": self._off_y.value(),
            "auto_hide": self._auto_hide.isChecked(),
            "auto_hide_delay_ms": self._hide_delay.value(),
            "pin_default": self._pin_default.isChecked(),
            "remember_geometry": self._remember.isChecked(),
            "panel_width": self._p_w.value(),
            "panel_height": self._p_h.value(),
            "send_auto_paste": self._send_paste.isChecked(),
            "text_mirror": self._text_mirror.isChecked(),
            "ignore_apps": ignore,
            "backup_keep": self._backup_keep.value(),
            "data_dir": chosen_dir,
        }

    def _on_accept(self) -> None:
        values = self._gather()
        if not values["hotkey"]:
            self._err(STR["settings_hotkey_bad"])
            return
        err = self._ops.apply(values)
        if err:
            self._err(err)
            return
        self.accept()

    @staticmethod
    def _err(msg: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(None, "中转站", msg)
