"""全局快捷键：RegisterHotKey + Qt 原生事件过滤（可在任意应用拖拽途中触发）。

规范序列格式："Ctrl+Alt+T"（修饰键顺序固定 Ctrl, Alt, Shift, Win）。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut, Qt

user32 = ctypes.windll.user32
# use_last_error 让 ctypes.get_last_error() 取到真实错误码（如 1409=已被占用）
_user32_err = ctypes.WinDLL("user32", use_last_error=True)

WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# Qt.Key → Windows VK（非字母数字部分）
_SPECIAL_VK = {
    Qt.Key.Key_Space: 0x20, Qt.Key.Key_Return: 0x0D, Qt.Key.Key_Enter: 0x0D,
    Qt.Key.Key_Escape: 0x1B, Qt.Key.Key_Tab: 0x09, Qt.Key.Key_Backspace: 0x08,
    Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Home: 0x24, Qt.Key.Key_End: 0x23,
    Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22,
    Qt.Key.Key_Left: 0x25, Qt.Key.Key_Up: 0x26,
    Qt.Key.Key_Right: 0x27, Qt.Key.Key_Down: 0x28,
}
_F1_BASE_QT = int(Qt.Key.Key_F1)
_F1_BASE_VK = 0x70


def qt_key_to_vk(qt_key: int) -> int | None:
    if 0x30 <= qt_key <= 0x39 or 0x41 <= qt_key <= 0x5A:  # 数字与字母同 VK
        return qt_key
    if _F1_BASE_QT <= qt_key <= _F1_BASE_QT + 23:
        return _F1_BASE_VK + (qt_key - _F1_BASE_QT)
    return _SPECIAL_VK.get(qt_key)


def _key_name(qt_key: int) -> str:
    """Qt key → 规范名（字母大写、特殊键友好名）。"""
    if 0x30 <= qt_key <= 0x39:
        return chr(qt_key)
    if 0x41 <= qt_key <= 0x5A:
        return chr(qt_key)
    names = {
        Qt.Key.Key_Space: "Space", Qt.Key.Key_Return: "Enter",
        Qt.Key.Key_Escape: "Esc", Qt.Key.Key_Tab: "Tab",
        Qt.Key.Key_Backspace: "Backspace", Qt.Key.Key_Delete: "Delete",
        Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Home: "Home",
        Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "PageUp",
        Qt.Key.Key_PageDown: "PageDown", Qt.Key.Key_Left: "Left",
        Qt.Key.Key_Up: "Up", Qt.Key.Key_Right: "Right", Qt.Key.Key_Down: "Down",
    }
    if qt_key in names:
        return names[qt_key]
    if _F1_BASE_QT <= qt_key <= _F1_BASE_QT + 23:
        return f"F{qt_key - _F1_BASE_QT + 1}"
    return ""


def sequence_to_canonical(seq: QKeySequence) -> str | None:
    """把 QKeySequenceEdit 的结果转规范序列；无效返回 None。

    规则：必须恰好一个键，且含 Ctrl/Alt/Win 之一（裸 Shift 或裸字母不注册全局热键）。
    """
    if seq.isEmpty() or seq.count() != 1:
        return None
    combo = seq[0]
    mods = combo.keyboardModifiers() if hasattr(combo, "keyboardModifiers") else Qt.KeyboardModifier(combo & 0xFFFF0000)
    qt_key = int(combo.key()) if hasattr(combo, "key") else int(combo & 0xFFFF)
    name = _key_name(qt_key)
    if not name or qt_key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
        return None
    parts = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if mods & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win")
    if mods & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if not any(m in parts for m in ("Ctrl", "Alt", "Win")):
        return None
    return "+".join(parts + [name])


def canonical_to_vk_mods(seq: str) -> tuple[int, int] | None:
    """规范序列 → (vk, mods)。"""
    parts = [p.strip() for p in (seq or "").split("+")]
    mods = 0
    key = ""
    for p in parts:
        p = p.strip()
        low = p.lower()
        if low == "ctrl":
            mods |= MOD_CONTROL
        elif low == "alt":
            mods |= MOD_ALT
        elif low == "shift":
            mods |= MOD_SHIFT
        elif low in ("win", "meta", "cmd"):
            mods |= MOD_WIN
        else:
            key = p
    if not key or not mods:
        return None
    qt_key = None
    if len(key) == 1 and key.isalnum():
        qt_key = ord(key.upper()) if key.isalpha() else ord(key)
    else:
        for qk, name in _SPECIAL_VK.items():
            if key.lower() == name.lower():
                qt_key = qk
                break
        else:
            if key.startswith("F") and key[1:].isdigit():
                n = int(key[1:])
                if 1 <= n <= 24:
                    qt_key = _F1_BASE_QT + n - 1
    vk = qt_key_to_vk(qt_key) if qt_key is not None else None
    if vk is None:
        return None
    return vk, mods


class HotkeyManager(QObject):
    """全局快捷键注册与管理。"""

    activated = Signal(str)  # 参数为规范序列

    _MOD_NAME_BITS = [
        ("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN),
    ]

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._filter = _HotkeyFilter(self._on_hotkey)
        self._filter_installed = False
        self._regs: dict[int, str] = {}   # hotkey id → 规范序列
        self._seq_id: dict[str, int] = {} # 序列 → id
        self._last_fire_ms: dict[str, int] = {}
        self._next_id = 0x1000
        _user32_err.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        _user32_err.RegisterHotKey.restype = wt.BOOL
        _user32_err.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
        _user32_err.UnregisterHotKey.restype = wt.BOOL

    def _ensure_filter(self) -> None:
        """把 WM_HOTKEY 原生过滤器装到应用上（只装一次，保持引用防回收）。"""
        if self._filter_installed:
            return
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        app.installNativeEventFilter(self._filter)
        self._filter_installed = True

    def _on_hotkey(self, hk_id: int) -> None:
        seq = self._regs.get(hk_id)
        if not seq:
            return
        # 去抖：长按会触发系统自动重复的 WM_HOTKEY，同一序列 400ms 内只响应一次
        import time

        now = int(time.monotonic() * 1000)
        last = self._last_fire_ms.get(seq, 0)
        if now - last < 400:
            return
        self._last_fire_ms[seq] = now
        self.activated.emit(seq)

    def register(self, seq: str) -> str | None:
        """注册；成功返回 None，失败返回错误信息。先反注册同名序列。"""
        self._ensure_filter()
        self.unregister(seq)
        pair = canonical_to_vk_mods(seq)
        if pair is None:
            return "快捷键格式无效"
        vk, mods = pair
        hk_id = self._next_id
        if not _user32_err.RegisterHotKey(None, hk_id, mods, vk):
            err = ctypes.get_last_error()
            return "已被其它程序占用" if err == ERROR_HOTKEY_ALREADY_REGISTERED else f"注册失败（错误 {err}）"
        self._next_id += 1
        self._regs[hk_id] = seq
        self._seq_id[seq] = hk_id
        return None

    def unregister(self, seq: str) -> None:
        hk_id = self._seq_id.pop(seq, None)
        if hk_id is None:
            return
        _user32_err.UnregisterHotKey(None, hk_id)
        self._regs.pop(hk_id, None)

    def unregister_all(self) -> None:
        for seq in list(self._seq_id):
            self.unregister(seq)


class _HotkeyFilter(QAbstractNativeEventFilter):
    """把 WM_HOTKEY 翻译为回调。"""

    def __init__(self, on_hotkey):
        super().__init__()
        self._on_hotkey = on_hotkey
        user32.GetMessageExtraInfo.restype = None

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = wt.MSG.from_address(int(message))
            except Exception:
                return False
            if msg.message == WM_HOTKEY:
                self._on_hotkey(int(msg.wParam) & 0xFFFF)
                return True
        return False
