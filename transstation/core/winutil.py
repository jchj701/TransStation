"""Win32 窗口/进程识别（ctypes，纯标准库，无 Qt 依赖）。

提供：前台窗口识别、光标下窗口识别、进程可执行文件显示名（FileDescription）、
忽略清单匹配（fnmatch 通配进程名）。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import fnmatch
from dataclasses import dataclass, field
from functools import lru_cache

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GA_ROOT = 2
SWP_NOACTIVATE = 0x0010

# 常见进程显示名覆盖（FileDescription 缺失或想统一时）
_DISPLAY_OVERRIDES = {
    "explorer.exe": "文件资源管理器",
    "applicationframehost.exe": "应用窗口",
}

_LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long


def _set_argtypes() -> None:
    user32.GetForegroundWindow.restype = wt.HWND
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.WindowFromPoint.argtypes = [wt.POINT]
    user32.WindowFromPoint.restype = wt.HWND
    user32.GetAncestor.argtypes = [wt.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wt.HWND
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsWindow.restype = wt.BOOL
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsIconic.restype = wt.BOOL
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wt.BOOL
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.SetForegroundWindow.restype = wt.BOOL
    user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_void_p]
    user32.keybd_event.restype = None
    kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
    kernel32.CloseHandle.argtypes = [wt.HANDLE]


_set_argtypes()


@dataclass
class AppInfo:
    """一次窗口识别结果。"""
    hwnd: int = 0
    pid: int = 0
    exe: str = ""        # 进程名，如 chrome.exe
    exe_path: str = ""   # 可执行文件完整路径
    title: str = ""      # 窗口标题
    name: str = ""       # 显示名（FileDescription / 覆盖表 / 进程名）

    @property
    def process_key(self) -> str:
        return self.exe.lower() if self.exe else self.title.strip().lower()

    def matched_by(self, patterns: list[str]) -> bool:
        """是否命中忽略清单：进程名优先；再比窗口标题（便于写宿主进程名雷同的场景）。
        模式含通配符时做 fnmatch；否则做包含匹配（对中文标题更顺手）。"""
        haystacks = [self.process_key]
        if self.title:
            haystacks.append(self.title.strip().lower())
        for pat in patterns or []:
            pat = pat.strip()
            if not pat:
                continue
            p = pat.lower()
            if any(ch in p for ch in "*?["):
                if any(fnmatch.fnmatch(h, p) for h in haystacks):
                    return True
            elif any(p in h for h in haystacks):
                return True
        return False


@lru_cache(maxsize=512)
def _display_name(exe_path: str) -> str:
    """读取 PE 的 FileDescription；失败回落覆盖表/进程名。"""
    key = _exe_key(exe_path)
    if key in _DISPLAY_OVERRIDES:
        return _DISPLAY_OVERRIDES[key]
    desc = _file_description(exe_path)
    if desc:
        return desc
    return key or ""


def _exe_key(exe_path: str) -> str:
    try:
        return exe_path.rsplit("\\", 1)[-1].lower()
    except Exception:
        return ""


def _file_description(path: str) -> str | None:
    """ctypes 读版本信息 FileDescription。"""
    try:
        ver = ctypes.WinDLL("version")
        size = ver.GetFileVersionInfoSizeW(path, None)
        if size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        # 子块: \VarFileInfo\Translation → \StringFileInfo\XXXX\FileDescription
        val = ctypes.c_void_p()
        val_len = ctypes.c_uint()
        ptr = ctypes.cast(buf, ctypes.c_void_p)
        if not ver.VerQueryValueW(
            ptr, "\\VarFileInfo\\Translation",
            ctypes.byref(val), ctypes.byref(val_len),
        ):
            return None
        lang = ctypes.string_at(val.value, 4)
        lang_id = f"{lang[0]:02X}{lang[1]:02X}"
        cp = f"{lang[2]:02X}{lang[3]:02X}"
        sub = f"\\StringFileInfo\\{lang_id}{cp}\\FileDescription"
        if not ver.VerQueryValueW(
            ptr, sub, ctypes.byref(val), ctypes.byref(val_len)
        ):
            sub = sub.replace(f"{lang_id}{cp}", "040904B0")  # 英文兜底
            if not ver.VerQueryValueW(
                ptr, sub, ctypes.byref(val), ctypes.byref(val_len)
            ):
                return None
        s = ctypes.wstring_at(val.value, val_len.value // 2)
        s = s.strip().rstrip("\x00")
        return s or None
    except Exception:
        return None


def _app_from_pid(pid: int, hwnd: int, title: str) -> AppInfo:
    info = AppInfo(hwnd=hwnd, pid=pid, title=title)
    if pid:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            try:
                bufsz = wt.DWORD(32768)
                buf = ctypes.create_unicode_buffer(bufsz.value)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(bufsz)):
                    info.exe_path = buf.value
                    info.exe = info.exe_path.rsplit("\\", 1)[-1]
            finally:
                kernel32.CloseHandle(h)
    info.name = _display_name(info.exe_path) if info.exe_path else (
        _DISPLAY_OVERRIDES.get(info.exe.lower(), "") or info.exe.rsplit(".", 1)[0]
        if info.exe else ""
    )
    if not info.name:
        info.name = (title or "").strip()[:24] or ""
    return info


def _hwnd_or_zero(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def app_for_window(hwnd: int) -> AppInfo | None:
    hwnd = _hwnd_or_zero(hwnd)
    if not hwnd:
        return None
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(512)
    n = user32.GetWindowTextW(hwnd, buf, 512)
    return _app_from_pid(pid.value, hwnd, buf.value[: max(n, 0)])


def foreground_app() -> AppInfo | None:
    return app_for_window(user32.GetForegroundWindow())


def window_at_point(x: int, y: int) -> AppInfo | None:
    """光标位置窗口（向上取根窗口）。"""
    pt = wt.POINT(x, y)
    hwnd = _hwnd_or_zero(user32.WindowFromPoint(pt))
    if not hwnd:
        return None
    root = _hwnd_or_zero(user32.GetAncestor(hwnd, GA_ROOT))
    return app_for_window(root or hwnd)


def is_same_process(pid: int) -> bool:
    """pid 是否属于当前进程。"""
    import os

    return pid == os.getpid()


def is_window_alive(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def activate_and_paste(hwnd: int) -> bool:
    """把窗口带到前台并发送一次 Ctrl+V（仅用于“发送到前台窗口”的可选自动粘贴）。"""
    if not is_window_alive(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if not user32.SetForegroundWindow(hwnd):
        # 用 ALT 键技巧绕过前台锁（模拟一次临时按键）
        user32.keybd_event(0x12, 0, 0, None)          # ALT down
        user32.keybd_event(0x12, 0, 0x0002, None)     # ALT up
        user32.SetForegroundWindow(hwnd)
    import time

    time.sleep(0.05)
    user32.keybd_event(0x11, 0, 0, None)              # CTRL down
    user32.keybd_event(0x56, 0, 0, None)              # V down
    user32.keybd_event(0x56, 0, 0x0002, None)         # V up
    user32.keybd_event(0x11, 0, 0x0002, None)         # CTRL up
    return True


def own_exe_key() -> str:
    """当前进程的 exe 名（用于剔除自家窗口）。"""
    import sys

    if getattr(sys, "frozen", False):
        return sys.executable.rsplit("\\", 1)[-1].lower()
    return "python.exe"
