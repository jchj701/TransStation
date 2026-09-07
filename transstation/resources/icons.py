"""自绘线性 SVG 图标集（24×24，描边占位符 {c} 渲染时替换为实际颜色）。

不允许使用 emoji/位图图标；托盘/面板图标统一走此处。
"""
from __future__ import annotations

# 通用线性图标：viewBox 0 0 24 24，stroke={c}，stroke-width 1.6，fill none
_TPL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

ICONS: dict[str, str] = {
    # 应用标识：对向箭头 + 方框（中转）
    "logo": _TPL.format(
        c="{c}",
        body=(
            '<rect x="3" y="3" width="18" height="18" rx="4.5"/>'
            '<path d="M9 8l-2.5 2.5L9 13"/>'
            '<path d="M15 16l2.5-2.5L15 11"/>'
            '<path d="M6.5 10.5H15"/>'
            '<path d="M17.5 13.5H9"/>'
        ),
    ),
    "file": _TPL.format(
        c="{c}",
        body=(
            '<path d="M6 3.5h7.5L18 8v11a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5A1.5 1.5 0 0 1 7.5 3.5h0z"/>'
            '<path d="M13.5 3.5V8H18"/>'
        ),
    ),
    "folder": _TPL.format(
        c="{c}",
        body=(
            '<path d="M3.5 7A1.5 1.5 0 0 1 5 5.5h4l2 2.5h8A1.5 1.5 0 0 1 20.5 9.5V17A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17z"/>'
            '<path d="M3.5 10.5h17"/>'
        ),
    ),
    "image": _TPL.format(
        c="{c}",
        body=(
            '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/>'
            '<circle cx="9" cy="10" r="1.8"/>'
            '<path d="M5.5 17l4.5-4.5 3 3 3-3 2.5 2.5"/>'
        ),
    ),
    "link": _TPL.format(
        c="{c}",
        body=(
            '<path d="M9.5 14.5l5-5"/>'
            '<path d="M11 6.8l1.6-1.6a3.8 3.8 0 0 1 5.4 5.4l-1.7 1.7"/>'
            '<path d="M13 17.2l-1.6 1.6a3.8 3.8 0 0 1-5.4-5.4l1.7-1.7"/>'
        ),
    ),
    "text": _TPL.format(
        c="{c}",
        body=(
            '<path d="M4.5 6.5h15"/>'
            '<path d="M4.5 12h15"/>'
            '<path d="M4.5 17.5h9"/>'
        ),
    ),
    "pin": _TPL.format(
        c="{c}",
        body=(
            '<path d="M9 4h6l-1 5.5 2.5 2.5H7.5L10 9.5z"/>'
            '<path d="M12 12v7.5"/>'
        ),
    ),
    "pinfill": _TPL.format(
        c="{c}",
        body=(
            '<path d="M9 4h6l-1 5.5 2.5 2.5H7.5L10 9.5z" fill="{c}" stroke="none"/>'
            '<path d="M12 12v7.5"/>'
        ),
    ),
    "close": _TPL.format(c="{c}", body='<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>'),
    "search": _TPL.format(
        c="{c}",
        body='<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    ),
    "gear": _TPL.format(
        c="{c}",
        body=(
            '<circle cx="12" cy="12" r="3.2"/>'
            '<path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2'
            "M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M17.9 6.1l-1.6 1.6M7.7 16.3l-1.6 1.6\"/>"
        ),
    ),
    "report": _TPL.format(
        c="{c}",
        body=(
            '<path d="M4.5 20.5h15"/>'
            '<rect x="6" y="11" width="3" height="6" rx="1"/>'
            '<rect x="10.5" y="7" width="3" height="10" rx="1"/>'
            '<rect x="15" y="4" width="3" height="13" rx="1"/>'
        ),
    ),
    "copy": _TPL.format(
        c="{c}",
        body=(
            '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/>'
            '<path d="M5.5 15.5h-1a1.5 1.5 0 0 1-1.5-1.5V5A1.5 1.5 0 0 1 4.5 3.5h9A1.5 1.5 0 0 1 15 5v1"/>'
        ),
    ),
    "clipboard_add": _TPL.format(
        c="{c}",
        body=(
            '<rect x="4.5" y="4.5" width="15" height="16" rx="2.5"/>'
            '<path d="M9 4.5a3 3 0 0 1 6 0"/>'
            '<path d="M12 10v6M9 13h6"/>'
        ),
    ),
    "send": _TPL.format(
        c="{c}",
        body=(
            '<path d="M4 12L20 5l-4.5 14-3.5-5z"/>'
            '<path d="M12 14l8-9"/>'
        ),
    ),
    "folder_open": _TPL.format(
        c="{c}",
        body=(
            '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6H10l2 2.5h6.5A1.5 1.5 0 0 1 20 10v.5H7l-3 8z"/>'
            '<path d="M5.5 19l2.7-7.5H20.5L18 19z"/>'
        ),
    ),
    "trash": _TPL.format(
        c="{c}",
        body=(
            '<path d="M4.5 6.5h15"/>'
            '<path d="M9 6.5V5A1.5 1.5 0 0 1 10.5 3.5h3A1.5 1.5 0 0 1 15 5v1.5"/>'
            '<path d="M6.5 6.5l1 13a1.5 1.5 0 0 0 1.5 1.4h6a1.5 1.5 0 0 0 1.5-1.4l1-13"/>'
            '<path d="M10 10.5v6M14 10.5v6"/>'
        ),
    ),
    "undo": _TPL.format(
        c="{c}",
        body=(
            '<path d="M8.5 5.5L4.5 9.5l4 4"/>'
            '<path d="M4.5 9.5h9a6 6 0 0 1 0 12h-4"/>'
        ),
    ),
    "error_dot": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6" fill="{c}"/></svg>',
    # 空状态插图（横幅版）
    "empty_state": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 120" fill="none">'
        '<rect x="18" y="14" width="120" height="92" rx="12" stroke="{c}" stroke-width="2"/>'
        '<rect x="30" y="28" width="96" height="64" rx="6" fill="{c}" fill-opacity="0.06"/>'
        '<path d="M52 52l10 10 8-7 10 9 14-14 16 15" stroke="{c}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M158 40h12a10 10 0 0 1 0 20h-12M162 44v12M172 44v12M148 44l6 6-6 6M118 20h-5" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
        '<path d="M36 108h148" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-dasharray="3 6" stroke-dashoffset="3"/>'
        "</svg>"
    ),
}


def svg_for(name: str, color: str = "#000000") -> bytes:
    """渲染带颜色占位符的 SVG 字节。"""
    raw = ICONS[name]
    return raw.replace("{c}", color).encode("utf-8")
