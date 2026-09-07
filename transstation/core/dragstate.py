"""拖拽状态检测：判断用户是否正处于一次跨应用拖拽中。

跨进程拖拽时无法用 GetCapture 得知（它只返回当前线程的捕获窗口），
实用判据：鼠标左键按住 + 前台应用不是自己。
"""
from __future__ import annotations

import ctypes

VK_LBUTTON = 0x01

user32 = ctypes.windll.user32


def left_button_down() -> bool:
    return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def likely_dragging() -> bool:
    """疑似拖拽中：左键按住即视为可能拖拽（面板呼出时不应抢焦点）。"""
    return left_button_down()
