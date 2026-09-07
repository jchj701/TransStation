"""winutil 通配匹配等纯逻辑测试（不依赖真实窗口）。"""
from transstation.core.winutil import AppInfo


def _app(exe: str = "", title: str = "") -> AppInfo:
    return AppInfo(hwnd=1, pid=1, exe=exe, title=title, exe_path="", name=exe or title)


def test_ignore_match_exact_and_wildcard():
    patterns = ["chrome.exe", "wechat*", "*notepad*"]
    assert _app(exe="chrome.exe").matched_by(patterns)
    assert _app(exe="WeChat.exe").matched_by(patterns)
    assert _app(exe="notepad++.exe").matched_by(patterns)
    assert not _app(exe="word.exe").matched_by(patterns)
    assert not _app(exe="").matched_by(patterns)


def test_ignore_fallback_to_title():
    pats = ["某特殊窗口"]
    info = _app(exe="weirdhost.exe", title="某特殊窗口 - 组")
    assert info.matched_by(pats)
    assert not _app(exe="weirdhost.exe", title="别的窗口").matched_by(pats)


def test_process_key_lowercased():
    assert _app(exe="CHROME.EXE").matched_by(["chrome.exe"])
