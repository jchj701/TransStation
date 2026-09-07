"""设计令牌：全部颜色/圆角/字号/间距集中在此，禁止在代码中硬编码色值。"""
from __future__ import annotations


def _darken(hex_color: str, f: float) -> str:
    """简易颜色压暗（返回 hex），仅用于派生悬停/按下态。"""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (max(0, int(c * (1 - f))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _mix(hex_color: str, hex_bg: str, t: float) -> str:
    """hex_color 与底色混合 t(0..1)，用于生成浅底强调色块。"""
    a = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    b = (int(hex_bg[i : i + 2], 16) for i in (1, 3, 5))
    m = tuple(int(av * (1 - t) + bv * t) for av, bv in zip(a, b))
    return f"#{m[0]:02x}{m[1]:02x}{m[2]:02x}"


COLORS = {
    "accent": "#3D6BF2",          # 强调色（蓝）
    "accent_strong": _darken("#3D6BF2", 0.12),
    "accent_soft": _mix("#3D6BF2", "#FFFFFF", 0.90),
    "danger": "#D64545",
    "warn": "#E6A23C",
    "ok": "#2FA96A",
    "text_primary": "#1F2329",
    "text_secondary": "#5A6270",
    "text_tertiary": "#8A93A2",
    "text_on_accent": "#FFFFFF",
    "surface": "#FFFFFF",
    "surface_hover": "#F4F6FA",
    "surface_active": "#EAEEF5",
    "surface_alt": "#F7F8FB",
    "border": "#E4E7ED",
    "border_strong": "#C9CFD9",
    "window_outer": "#00000000",  # 窗口外透明
    "shadow": "rgba(16,24,40,0.12)",
    "kind_file": "#4E7CF0",       # 类型色：文件
    "kind_folder": "#B07BE0",
    "kind_image": "#2FA96A",
    "kind_link": "#2E9BE6",
    "kind_text": "#8A93A2",
}

RADIUS = {"window": 12, "card": 10, "control": 6, "chip": 999}

FONT = {
    "family": ["Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI"],
    "size_base": 13,
    "size_small": 11.5,
    "size_tiny": 10.5,
    "size_title": 14.5,
}

SPACING = {"gap": 8, "gap_l": 12, "margin": 10, "header": 32, "status": 30}

MOTION = {"fast": 120, "normal": 150, "slow": 200}

PANEL = {
    "width": 460,
    "height": 620,
    "min_width": 320,
    "min_height": 360,
    "popup_offset_x": 18,   # 呼出时相对光标偏移（px）
    "popup_offset_y": 14,
}

LIMITS = {
    "text_max_chars": 200_000,       # 文本条目内容上限
    "page_size": 150,                # 列表分批加载条数
    "thumb_size": 128,               # 缩略图边长上限
    "recycle_days": 30,              # 回收站保留天数
    "default_backup_keep": 7,        # 备份默认保留份数
}
