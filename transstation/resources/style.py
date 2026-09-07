"""样式基础设施：字体、图标渲染缓存、QSS 构建、系统“减少动画”检测。"""
from __future__ import annotations

import ctypes
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from transstation.resources.icons import svg_for
from transstation.resources.tokens import COLORS, FONT, RADIUS, SPACING


def setup_application_font() -> None:
    """统一中英文字体：拉丁优先 Segoe UI Variable，中文由系统回退到 YaHei。"""
    candidates = [f for f in FONT["family"] if f in QFontDatabase.families()]
    family = candidates[0] if candidates else "Microsoft YaHei UI"
    font = QFont(family)
    font.setPixelSize(14)
    QApplication.instance().setFont(font)


def force_light_palette() -> None:
    """强制浅色 Fusion 调色板。

    深色系统主题下 Qt 6.5+ 会让 Fusion 自动跟随生成深色调色板，而我们只通过
    QSS 覆盖了部分控件——未覆盖处（右键菜单/消息框等）会变成“深底+全局深字”，
    即用户遇到的“黑底黑字”。此处显式压回浅色，保证整应用外观一致。
    """
    app = QApplication.instance()
    hints = app.styleHints()
    try:
        hints.setColorScheme(Qt.ColorScheme.Light)
    except Exception:
        pass
    pal = app.palette()
    c = COLORS
    pal.setColor(QPalette.ColorRole.Window, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text_primary"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface_alt"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text_primary"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text_primary"]))
    pal.setColor(QPalette.ColorRole.BrightText, QColor(c["text_on_accent"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(c["text_on_accent"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text_primary"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_tertiary"]))
    disabled = QPalette.ColorGroup.Disabled
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        pal.setColor(disabled, role, QColor(c["text_tertiary"]))
    app.setPalette(pal)


@lru_cache(maxsize=256)
def icon_pixmap(name: str, color: str, size: int, dpr: float = 1.0) -> QPixmap:
    """把线性 SVG 渲染为带颜色、DPR 感知的 QPixmap（带缓存）。"""
    renderer = QSvgRenderer(QByteArray(svg_for(name, color)))
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, px.width(), px.height()))
    painter.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str, size: int) -> QIcon:
    """小图标：同时产出 1x/2x 供高分屏。"""
    icon_ = QIcon()
    for dpr in (1.0, 2.0):
        icon_.addPixmap(icon_pixmap(name, color, size, dpr))
    return icon_


def css_rgb(color: str) -> str:
    """hex 或 rgba 字符串在 QSS 中可直接使用；仅统一入口。"""
    return color


def build_qss() -> str:
    """全应用 QSS。颜色一律来自 tokens。"""
    c = COLORS
    return f"""
* {{ outline: none; }}
QWidget {{
    font-family: "Segoe UI Variable","Segoe UI","Microsoft YaHei UI";
    color: {c['text_primary']};
}}
QToolTip {{
    background: #262B33; color: #F2F4F8; border: none;
    padding: 4px 8px; border-radius: 4px;
}}

/* ---- 面板表面与顶层控件 ---- */
QFrame#PanelSurface {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: {RADIUS['window']}px;
}}
QFrame#PanelSurface[dropHover="true"] {{
    border: 2px solid {c['accent']};
    background: {c['accent_soft']};
}}
QLabel#PanelSurfaceLabel {{
    background: transparent;
    border: none;
    border-radius: {RADIUS['window']}px;
}}
QLabel#DropHintLabel {{
    background: {c['accent']};
    color: {c['text_on_accent']};
    border-radius: 999px;
    padding: 7px 16px;
    font-weight: 600;
}}

/* ---- 标题栏 ---- */
QLabel#AppTitle {{ font-weight: 600; color: {c['text_primary']}; }}
QLabel#SourceChip {{
    color: {c['text_secondary']};
    background: {c['surface_alt']};
    border: 1px solid {c['border']};
    border-radius: 999px;
    padding: 1px 8px;
    font-size: 11px;
}}

/* ---- 图标按钮（标题栏 / 状态栏）---- */
QToolButton#IconBtn {{
    border: none; border-radius: {RADIUS['control']}px;
    background: transparent;
}}
QToolButton#IconBtn:hover {{ background: {c['surface_hover']}; }}
QToolButton#IconBtn:pressed {{ background: {c['surface_active']}; }}
QToolButton#IconBtn:checked {{
    background: {c['accent_soft']};
}}

/* ---- 搜索框 ---- */
QLineEdit#SearchBox {{
    border: 1px solid {c['border']};
    border-radius: {RADIUS['control']}px;
    padding: 5px 28px 5px 10px;
    background: {c['surface_alt']};
    selection-background-color: {c['accent']};
    selection-color: {c['text_on_accent']};
}}
QLineEdit#SearchBox:focus {{
    border: 1px solid {c['accent']};
    background: {c['surface']};
}}

/* ---- 筛选 chips ---- */
QToolButton#FilterChip {{
    border: 1px solid {c['border']};
    border-radius: 999px;
    background: {c['surface']};
    color: {c['text_secondary']};
    padding: 2px 10px;
    font-size: 11px;
}}
QToolButton#FilterChip:hover {{ background: {c['surface_hover']}; color: {c['text_primary']}; }}
QToolButton#FilterChip:checked {{
    background: {c['text_primary']};
    color: #FFFFFF;
    border-color: {c['text_primary']};
}}

/* ---- 列表 ---- */
QListView#CardList {{
    background: transparent;
    border: none;
}}
QListView#CardList::item {{ background: transparent; }}

/* ---- 状态栏按钮 ---- */
QToolButton#StatusBtn {{
    border: none; border-radius: {RADIUS['control']}px;
    background: transparent; color: {c['text_secondary']};
    padding: 2px 6px;
}}
QToolButton#StatusBtn:hover {{ background: {c['surface_hover']}; color: {c['text_primary']}; }}
QToolButton#StatusBtn:disabled {{ color: {c['border_strong']}; }}

/* ---- Toast ---- */
QFrame#ToastBar {{
    background: #262B33;
    border-radius: 8px;
}}
QLabel#ToastText {{ color: #F2F4F8; background: transparent; }}
QPushButton#ToastBtn {{
    color: #AFC4FF; background: transparent; border: none;
    font-weight: 600; padding: 2px 4px; border-radius: 4px;
}}
QPushButton#ToastBtn:hover {{ background: rgba(255,255,255,0.14); }}
QPushButton#ToastBtn:pressed {{ background: rgba(255,255,255,0.22); }}

/* ---- 弹出菜单（显式浅色样式，防止深色系统主题串色成“黑底黑字”） ---- */
QMenu {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    background: transparent;
    color: {c['text_primary']};
    padding: 6px 28px 6px 12px;
    border-radius: 5px;
}}
QMenu::item:selected {{ background: {c['surface_hover']}; }}
QMenu::item:disabled {{ color: {c['border_strong']}; }}
QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 5px 8px;
}}

/* ---- 通用对话框与控件 ---- */
QDialog {{
    background: {c['surface']};
}}
QGroupBox {{
    border: 1px solid {c['border']};
    border-radius: {RADIUS['control'] + 2}px;
    margin-top: 8px;
    padding-top: 6px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px;
    padding: 0 4px;
    color: {c['text_secondary']};
}}
QPushButton {{
    border: 1px solid {c['border_strong']};
    border-radius: {RADIUS['control']}px;
    background: {c['surface']};
    padding: 5px 14px;
}}
QPushButton:hover {{ background: {c['surface_hover']}; }}
QPushButton:pressed {{ background: {c['surface_active']}; }}
QPushButton:disabled {{ color: {c['border_strong']}; background: {c['surface_alt']}; border-color: {c['border']}; }}
QPushButton#PrimaryBtn {{
    background: {c['accent']}; color: {c['text_on_accent']};
    border: none; font-weight: 600;
}}
QPushButton#PrimaryBtn:hover {{ background: {c['accent_strong']}; }}
QPushButton#DangerBtn {{ color: {c['danger']}; }}
QLineEdit, QSpinBox, QPlainTextEdit, QTextEdit, QKeySequenceEdit {{
    border: 1px solid {c['border']};
    border-radius: {RADIUS['control']}px;
    padding: 4px 8px;
    background: {c['surface']};
    selection-background-color: {c['accent']};
    selection-color: {c['text_on_accent']};
}}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus, QKeySequenceEdit:focus {{
    border-color: {c['accent']};
}}
QCheckBox {{ spacing: 6px; }}
QListWidget {{
    border: 1px solid {c['border']};
    border-radius: {RADIUS['control']}px;
    background: {c['surface']};
}}
QListWidget::item {{ padding: 3px 6px; border-radius: 4px; }}
QListWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text_primary']}; }}
QListWidget::item:hover {{ background: {c['surface_hover']}; }}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['border_strong']}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #A8B0BD; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def system_reduce_motion() -> bool:
    """读取 Windows“辅助功能→视觉效果→动画效果”设置（SPI_GETCLIENTAREAANIMATION）。"""
    try:
        user32 = ctypes.windll.user32
        enabled = ctypes.c_bool(True)
        ok = user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(ok) and not bool(enabled.value)
    except Exception:
        return False
