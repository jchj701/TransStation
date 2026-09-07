"""时间显示工具（纯逻辑，无 Qt 依赖）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from transstation.resources.strings_zh import STR


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def rel_time(iso: str | None, now: datetime | None = None) -> str:
    """相对时间：刚刚 / n 分钟前 / n 小时前 / 今天 HH:MM / 昨天 HH:MM / MM-DD。"""
    dt = parse_iso(iso or "")
    if dt is None:
        return ""
    now = now or datetime.now()
    delta = now - dt
    if delta.total_seconds() < 60:
        return STR["time_just_now"]
    if delta.total_seconds() < 3600:
        return STR["time_min_ago"].format(n=max(1, int(delta.total_seconds() // 60)))
    if delta.total_seconds() < 86400 and dt.date() == now.date():
        return dt.strftime("%H:%M")
    if dt.date() == (now - timedelta(days=1)).date():
        return STR["time_yesterday"].format(t=dt.strftime("%H:%M"))
    if dt.year == now.year:
        return dt.strftime("%m-%d")
    return dt.strftime("%Y-%m-%d")


def clock_hms(dt: datetime | None = None) -> str:
    return (dt or datetime.now()).strftime("%H:%M:%S")
