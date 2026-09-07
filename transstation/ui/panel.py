"""呼出式浮窗面板：面板 UI + OLE 拖入目标 + 浏览/搜索/筛选 + 收起逻辑。

交互细则：
- 呼出位置跟随光标（多屏工作区内夹取），出现/收起动画 ≤200ms；
- 存入后按设置延时自动收起；Esc / 点击外部 / 再按热键可收起；钉住时不自动收起；
- 拖入悬停整窗高亮并显示“松开鼠标存入”；拖出面板区域即取消该次拖放；
- 面板置顶（WindowStaysOnTopHint）；疑似拖拽中呼出不抢焦点。
"""
from __future__ import annotations

import logging

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPixmap, QCursor, QGuiApplication, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from transstation.core import dragstate, winutil
from transstation.core.kinds import RawPayload, parse_payload
from transstation.olednd import payload as ole
from transstation.resources.icons import svg_for
from transstation.resources.strings_zh import STR
from transstation.resources.style import icon, icon_pixmap
from transstation.resources.tokens import COLORS, MOTION, PANEL, SPACING
from transstation.store.db import Store
from transstation.store.settings import Settings
from transstation.ui.cards import CardList
from transstation.ui.common import chip_button, icon_button, update_icon
from transstation.ui.onboarding import OnboardingOverlay
from transstation.ui.toast import ToastBar

log = logging.getLogger(__name__)

DROP_TOAST_MS = 2800  # 存入提示（含撤销按钮）的最短停留时间
SESSION_TIMEOUT_MS = 6000  # 呼出后无任何交互/拖入的自动收起时长（后续版本可配置）


def _now_ms() -> int:
    import time

    return int(time.monotonic() * 1000)


def _screen_dpr() -> float:
    try:
        scr = QGuiApplication.screenAt(QCursor.pos())
        return scr.devicePixelRatio() if scr else 1.0
    except Exception:
        return 1.0


class NoDropLineEdit(QLineEdit):
    """搜索框不参与 OLE 拖放（拖放事件统一由面板处理）。"""

    def dragEnterEvent(self, e):
        e.ignore()

    def dragMoveEvent(self, e):
        e.ignore()

    def dragLeaveEvent(self, e):
        e.ignore()

    def dropEvent(self, e):
        e.ignore()


class _ElideLabel(QLabel):
    """空间不足时以省略号截断文本（QLabel 默认直接裁剪），全文放 tooltip。"""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__("", parent)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        # 真实 setText 保证 sizeHint/布局按全文计算；绘制时再做省略截断
        super().setText(text)
        self.setToolTip(text)
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QFontMetrics

        text = super().text()
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight,
                               max(self.width() - 12, 10))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QColor(self.palette().color(self.foregroundRole())))
        painter.drawText(self.rect().adjusted(8, 0, -4, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
        painter.end()


class ResizeHandle(QWidget):
    """右下角缩放把手（自绘三角 + 手动改几何，兼容无边框窗口）。"""

    def __init__(self, panel: "Panel"):
        super().__init__(panel)
        self._panel = panel
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("拖动调整面板大小")
        self._start = None
        self._start_geom = None
        self._moved = False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QColor(COLORS["border_strong"]))
        for i in range(2):
            x = self.width() - 7 - i * 4
            y = self.height() - 1 - i * 4 - 2
            p.drawLine(x, self.height(), self.width(), y)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.globalPosition().toPoint()
            self._start_geom = self._panel.geometry()
            self._moved = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        d = e.globalPosition().toPoint() - self._start
        g = self._start_geom
        self._panel.resize(
            max(PANEL["min_width"], g.width() + d.x()),
            max(PANEL["min_height"], g.height() + d.y()),
        )
        self._moved = True

    def mouseReleaseEvent(self, e):
        if self._start is not None and self._moved:
            self._panel.save_geometry()
        self._start = None


class Panel(QWidget):
    """中转站浮窗。不能自理的动作通过信号交给 AppController。"""

    request_open = Signal(object)           # Item
    request_menu = Signal(object, object)   # (Item, 全局 QPoint)
    request_drag = Signal(object, object)   # (Item, 全局按下点)
    request_clipboard_add = Signal()
    request_settings = Signal()
    hidden_manually = Signal()

    def __init__(self, store: Store, settings: Settings, hotkey_text: str = "Ctrl+Alt+T"):
        super().__init__(None)
        self._store = store
        self._settings = settings
        self._hotkey_text = hotkey_text

        self.pinned = bool(settings.get("pin_default"))
        self._pin_pos: QPoint | None = None   # 钉住时记忆的位置（本会话内）
        self._ctx_app = None                  # 呼出/切走时记录的前台应用
        self._drag_state: str | None = None   # None / over / canceled
        self._undo_cb = None
        self._hide_scheduled = False
        self._anim: QPropertyAnimation | None = None
        self._last_active_ms: int = 0   # 最近一次面板活动时刻（会话看门狗用）

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("中转站")
        self.setAcceptDrops(True)
        self.resize(int(settings.get("panel_width")), int(settings.get("panel_height")))

        self._surface = QFrame(self)
        self._surface.setObjectName("PanelSurface")
        self._surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._surface.setGeometry(self.rect())
        surf = QVBoxLayout(self._surface)
        surf.setContentsMargins(SPACING["margin"], 8, SPACING["margin"], 5)
        surf.setSpacing(5)

        self._build_header(surf)
        self._build_search(surf)
        self._build_filters(surf)
        self._build_body(surf)
        self._build_status(surf)

        # 拖放提示徽标（跟随表面定位）
        self._drop_hint = QLabel(STR["drop_hint"], self._surface)
        self._drop_hint.setObjectName("DropHintLabel")
        self._drop_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._drop_hint.hide()

        # Toast（浮在列表底部）
        self._toast = ToastBar(self._surface)
        self._toast.undo_requested.connect(self._on_undo)

        # 新手引导（完成后置空，本会话不再弹出）
        self._onboard = None
        if store.meta_get("onboarded") != "1":

            def _onboard_done():
                store.meta_set("onboarded", "1")
                self._onboard = None

            self._onboard = OnboardingOverlay(self._surface, on_done=_onboard_done)
            self._onboard.hide()

        # 缩放把手
        self._grip = ResizeHandle(self._surface)

        # 快捷键（窗口获得焦点时生效）
        QShortcut(QKeySequence("Escape"), self, activated=self.hide_panel)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.focus_search)

        # 空闲监视：点击外部 / 拖拽取消后的自动收起
        self._idle = QTimer(self)
        self._idle.setInterval(90)
        self._idle.timeout.connect(self._on_idle)

        # 搜索防抖
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.reload)

        self._wire_list()
        QApplication.instance().installEventFilter(self)
        self.sync_pin_ui()

    # ================= 构建 =================
    def _build_header(self, surf: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(icon_pixmap("logo", COLORS["accent"], 16))
        row.addWidget(logo)
        title = QLabel(STR["app_title_short"])
        title.setObjectName("AppTitle")
        row.addWidget(title)
        self._src_chip = _ElideLabel("")
        self._src_chip.setObjectName("SourceChip")
        self._src_chip.hide()
        row.addWidget(self._src_chip, 1)
        row.addStretch(0)
        self._btn_add = icon_button("clipboard_add", STR["btn_clipboard_add"], 17)
        self._btn_add.clicked.connect(self.request_clipboard_add.emit)
        row.addWidget(self._btn_add)
        self._btn_pin = icon_button("pin", STR["menu_pin"], 16, checkable=True)
        self._btn_pin.clicked.connect(self._toggle_pin)
        row.addWidget(self._btn_pin)
        self._btn_close = icon_button("close", STR["close"], 15)
        self._btn_close.clicked.connect(self.hide_panel)
        row.addWidget(self._btn_close)
        surf.addLayout(row)

    def _build_search(self, surf: QVBoxLayout) -> None:
        from PySide6.QtGui import QAction

        self._search = NoDropLineEdit()
        self._search.setObjectName("SearchBox")
        self._search.setPlaceholderText(STR["search_placeholder"])
        self._search.textChanged.connect(lambda _t: self._search_timer.start())
        # 自绘清空按钮（保持图标全部线性 SVG 的约定）
        clear_act = QAction(icon("close", COLORS["text_tertiary"], 11), "", self._search)
        clear_act.setToolTip("清空")
        clear_act.triggered.connect(self._search.clear)
        self._search.addAction(clear_act, QLineEdit.ActionPosition.TrailingPosition)
        surf.addWidget(self._search)

    def _build_filters(self, surf: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(4)
        self._chips: dict[str, object] = {}
        texts = {
            "all": STR["filter_all"], "file": STR["filter_file"],
            "link": STR["filter_link"], "text": STR["filter_text"],
            "image": STR["filter_image"],
        }
        for key, text in texts.items():
            btn = chip_button(text)
            btn.clicked.connect(lambda _=False, k=key: self._on_filter(k))
            self._chips[key] = btn
            row.addWidget(btn)
        self._chips["all"].setChecked(True)
        row.addStretch(1)
        surf.addLayout(row)

    def _build_body(self, surf: QVBoxLayout) -> None:
        self._list = CardList()
        self._list.setAcceptDrops(True)
        self._list.viewport().setMouseTracking(True)

        # 空状态页
        empty = QWidget()
        elay = QVBoxLayout(empty)
        elay.setContentsMargins(24, 8, 24, 12)
        elay.addStretch(1)
        art = QLabel()
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setPixmap(_svg_pixmap_scaled("empty_state", COLORS["text_tertiary"], 200))
        elay.addWidget(art)
        self._empty_title = QLabel("")
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setStyleSheet("color:#5A6270;font-size:14px;font-weight:600;")
        self._empty_title.setWordWrap(True)
        elay.addWidget(self._empty_title)
        self._empty_desc = QLabel("")
        self._empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_desc.setStyleSheet("color:#8A93A2;font-size:12px;")
        self._empty_desc.setWordWrap(True)
        elay.addWidget(self._empty_desc)
        self._empty_btn = QPushButton(STR["btn_try_clipboard"])
        self._empty_btn.setObjectName("PrimaryBtn")
        self._empty_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._empty_btn.setMaximumWidth(180)
        self._empty_btn.clicked.connect(self.request_clipboard_add.emit)
        self._empty_btn.hide()
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self._empty_btn)
        btn_row.addStretch(1)
        elay.addLayout(btn_row)
        elay.addStretch(2)

        self._stack = _Stack(self._surface)
        self._stack.add_widget(self._list)
        self._stack.add_widget(empty)
        surf.addWidget(self._stack, 1)

    def _build_status(self, surf: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(2)
        row.setContentsMargins(0, 0, 16, 0)  # 右下角留给缩放把手
        self._counts = QLabel("")
        self._counts.setStyleSheet("color:#8A93A2;font-size:11px;")
        row.addWidget(self._counts)
        row.addStretch(1)
        btn_report = icon_button("report", STR["status_report"], 15)
        btn_report.setEnabled(False)
        btn_report.setToolTip(STR["report_disabled"])
        row.addWidget(btn_report)
        btn_settings = icon_button("gear", STR["status_settings"], 15)
        btn_settings.clicked.connect(self.request_settings.emit)
        row.addWidget(btn_settings)
        surf.addLayout(row)

    def _wire_list(self) -> None:
        self._list.activated_item.connect(self.request_open.emit)
        self._list.context_item.connect(self.request_menu.emit)
        self._list.drag_started.connect(self.request_drag.emit)
        self._list.load_more_needed.connect(self._load_more)

    # ================= 查询与刷新 =================
    @property
    def current_kind(self) -> str:
        for key, btn in self._chips.items():
            if btn.isChecked():
                return key
        return "all"

    def current_search(self) -> str:
        return self._search.text().strip()

    def reload(self, *, reset_scroll: bool = True) -> None:
        page = self._store.list_items(
            kind=self.current_kind, search=self.current_search() or None,
            limit=200, offset=0,
        )
        self._list.reset_items(page)
        if reset_scroll:
            self._list.scrollToTop()
        self._update_empty_state()
        self._update_counts()

    def _load_more(self) -> None:
        offset = len(self._list.model_items().items)
        more = self._store.list_items(
            kind=self.current_kind, search=self.current_search() or None,
            limit=200, offset=offset,
        )
        if more:
            self._list.append_items(more)
            self._update_counts()

    def notify_list_changed(self) -> None:
        """集合变化（存入/删除/恢复/剪贴板添加）后的全量刷新。"""
        self.reload(reset_scroll=False)

    def notify_item_changed(self, item_id: int) -> None:
        it = self._store.get_active(item_id)
        if it is not None:
            self._list.replace_item(it)
        self._update_counts()

    def _update_counts(self) -> None:
        total = self._store.count_items(deleted=False)
        weekly = self._store.weekly_use_count()
        self._counts.setText(STR["status_counts"].format(total=total, weekly=weekly))

    def _update_empty_state(self) -> None:
        has_rows = self._list.model_items().rowCount() > 0
        self._stack.set_page(0 if has_rows else 1)
        if has_rows:
            return
        if self.current_search():
            self._empty_title.setText("没有匹配的条目")
            self._empty_desc.setText("换个关键词试试")
            self._empty_btn.hide()
        else:
            self._empty_title.setText(STR["empty_title"])
            self._empty_desc.setText(
                STR["empty_desc"].format(hotkey=self._hotkey_text) + "\n" + STR["empty_desc2"]
            )
            self._empty_btn.show()

    def _on_filter(self, key: str) -> None:
        self.reload()

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    # ================= 显示 / 收起 =================
    def reduce_motion(self) -> bool:
        manual = self._settings.get("reduce_motion")
        return manual if manual is not None else _system_reduce_motion()

    def is_visible(self) -> bool:
        return self.isVisible()

    def context_app(self):
        """最近一次记录到的“用户所在的外部应用”。"""
        return self._ctx_app

    def show_panel(self, from_hotkey: bool = True) -> None:
        """呼出：记录前台应用 → 跟随光标 → 显示（拖拽中不抢焦点）。"""
        log.debug("show_panel: visible=%s pinned=%s cursor=%s",
                  self.isVisible(), self.pinned, QCursor.pos())
        self._ctx_app = self._capture_context()
        if self.isVisible():
            # 已可见：拖拽中/投放悬停中/钉住 → 保持（避免长按或连续拖动打断会话）；
            # 否则视为“再按一次收起”
            if (
                self.pinned
                or dragstate.left_button_down()
                or self._drag_state is not None
            ):
                self._refresh_ctx_chip()
                self.reload()
                self.raise_()
                self._flash()
                log.debug("热键重复/拖拽中：保持面板")
            else:
                log.debug("热键切换：收起面板")
                self.hide_panel()
            return

        dragging = dragstate.likely_dragging()
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, dragging)
        self._refresh_ctx_chip()

        if self.pinned and self._pin_pos is not None:
            self.move(self._pin_pos)
        else:
            self._place_near_cursor()
        self._drag_state = None
        # 注意：必须直接动画 windowOpacity（顶层窗口用透明度特效层会不生效/闪黑）
        if self.reduce_motion():
            self.setWindowOpacity(1.0)
        else:
            self.setWindowOpacity(0.0)
        log.debug("show_panel: 即将 show")
        self.show()
        log.debug("show_panel: 已 show")
        self._surface.setGeometry(self.rect())
        self._relayout_overlays()
        self.raise_()
        self._last_active_ms = _now_ms()
        if not dragging:
            self.activateWindow()
        log.debug("show_panel: 开始淡入")
        self._fade(1.0, from_value=0.0)
        self._idle.start()
        if self._onboard is not None:
            self._onboard.setGeometry(self._surface.rect())
            self._onboard.show()
            self._onboard.raise_()
        log.debug("show_panel: 刷新列表")
        self.reload()
        try:
            import ctypes
            import ctypes.wintypes as _wt

            r = _wt.RECT()
            hwnd = int(self.winId())
            user32_probe = ctypes.windll.user32
            user32_probe.GetWindowRect.argtypes = [_wt.HWND, ctypes.POINTER(_wt.RECT)]
            if user32_probe.GetWindowRect(hwnd, ctypes.byref(r)):
                log.debug("show: rect_physical=%d,%d,%d,%d", r.left, r.top, r.right, r.bottom)
            else:
                log.debug("show: rect_physical=unavailable")
        except Exception as e:
            log.debug("show: rect_physical 获取失败 %r", e)

    def hide_panel(self) -> None:
        if not self.isVisible():
            return
        if self._anim is not None and self._anim.state() == QPropertyAnimation.State.Running:
            return
        if self._onboard is not None:
            self._onboard.hide()
        self._toast.cancel()
        self._idle.stop()
        self._hide_scheduled = False
        self._save_pin_pos()
        if self.reduce_motion():
            self.hide()
            return
        self._fade(0.0, on_finish=self.hide)

    def _request_auto_hide(self) -> None:
        """存入后的自动收起（提示条读完再收，钉住/关闭自动收起时不动作）。"""
        if self.pinned or not self.isVisible() or not self._settings.get("auto_hide"):
            return
        delay = max(int(self._settings.get("auto_hide_delay_ms")), DROP_TOAST_MS)
        self._hide_scheduled = True
        QTimer.singleShot(delay, self._auto_hide_tick)

    def _auto_hide_tick(self) -> None:
        if not (self._hide_scheduled and self.isVisible() and not self.pinned):
            return
        # 用户光标正悬停在面板上浏览 → 顺延一次
        if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            QTimer.singleShot(800, self._auto_hide_tick)
            return
        self.hide_panel()

    def _flash(self) -> None:
        if self.reduce_motion():
            return
        self._fade(1.0)

    # ---------- 动画（直接作用于 windowOpacity，顶层窗口安全） ----------
    def _fade(self, target: float, from_value: float | None = None, on_finish=None) -> None:
        if self.reduce_motion():
            if on_finish:
                on_finish()
            return
        if from_value is not None:
            self.setWindowOpacity(from_value)
        if self._anim is not None and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(MOTION["normal"])
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        if on_finish:
            anim.finished.connect(on_finish)
        self._anim = anim
        anim.start()

    # ---------- 定位与几何 ----------
    def _place_near_cursor(self) -> None:
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos)
        wa = (screen or QGuiApplication.primaryScreen()).availableGeometry()
        w, h = self.width(), self.height()
        ox = int(self._settings.get("popup_offset_x"))
        oy = int(self._settings.get("popup_offset_y"))
        x = pos.x() + ox
        y = pos.y() + oy
        if x > wa.right() - w - 6:          # 右侧放不下 → 光标左侧
            x = pos.x() - w - ox
        if y > wa.bottom() - h - 6:         # 下方放不下 → 光标上方
            y = pos.y() - h - oy
        x = min(max(x, wa.left() + 6), wa.right() - w - 6)
        y = min(max(y, wa.top() + 6), wa.bottom() - h - 6)
        self.move(x, y)

    def save_geometry(self) -> None:
        if not self._settings.get("remember_geometry"):
            return
        self._settings.set("panel_width", self.width())
        self._settings.set("panel_height", self.height())
        self._settings.save()

    def _save_pin_pos(self) -> None:
        if self.pinned and self._settings.get("remember_geometry"):
            self._pin_pos = self.pos()

    def _relayout_overlays(self) -> None:
        r = self._surface.rect()
        self._drop_hint.adjustSize()
        self._drop_hint.move(
            (r.width() - self._drop_hint.width()) // 2,
            r.top() + int(r.height() * 0.2),
        )
        self._grip.move(r.right() - self._grip.width() - 1, r.bottom() - self._grip.height() - 1)
        tw = min(340, r.width() - 40)
        self._toast.setGeometry(r.left() + (r.width() - tw) // 2, r.bottom() - 58, tw, 40)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._surface.setGeometry(self.rect())
        self._relayout_overlays()

    # ---------- 上下文（来源/发送目标） ----------
    def _capture_context(self):
        app = winutil.foreground_app()
        if app is None or winutil.is_same_process(app.pid):
            return None
        return app

    def _refresh_ctx_chip(self) -> None:
        ctx = self._ctx_app
        if ctx and ctx.name:
            self._src_chip.set_full_text(STR["panel_source_from"].format(app=ctx.name))
            self._src_chip.show()
        else:
            self._src_chip.hide()

    def _remember_deactivated_app(self) -> None:
        """失焦后记住刚被激活的外部应用（作发送到前台窗口的目标）。"""
        if not self.isVisible():
            return

        def tick():
            app = winutil.foreground_app()
            if app is None or winutil.is_same_process(app.pid):
                return
            self._ctx_app = app
            self._refresh_ctx_chip()

        QTimer.singleShot(180, tick)

    # ---------- 钉住 ----------
    def _toggle_pin(self) -> None:
        self.set_pinned(not self.pinned)

    def set_pinned(self, on: bool) -> None:
        self.pinned = on
        self._btn_pin.setChecked(on)
        update_icon(self._btn_pin, "pinfill" if on else "pin",
                    COLORS["warn"] if on else COLORS["text_secondary"])
        self._btn_pin.setToolTip(STR["menu_unpin"] if on else STR["menu_pin"])
        if on and self.isVisible():
            self._save_pin_pos()
        if self.isVisible():
            if on:
                self._idle.stop()
            else:
                self._idle.start()

    def sync_pin_ui(self) -> None:
        self.set_pinned(self.pinned)

    # ================= OLE 拖放（接收端） =================
    def _mime_acceptable(self, mime) -> bool:
        return bool(mime and (mime.hasUrls() or mime.hasText() or mime.hasHtml() or mime.hasImage()))

    def dragEnterEvent(self, event) -> None:
        if not self._mime_acceptable(event.mimeData()):
            log.debug("dragEnter 拒绝: %s", event.mimeData().formats())
            event.ignore()
            return
        log.debug("dragEnter 接受, formats=%s", event.mimeData().formats())
        # 拖放途中不看引导页
        if self._onboard is not None and self._onboard.isVisible():
            self._onboard.hide()
        self._drag_state = "over"
        event.acceptProposedAction()
        self._set_drop_hover(True)
        self._show_drop_hint(True)

    def dragMoveEvent(self, event) -> None:
        if self._drag_state != "canceled" and self._mime_acceptable(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        # 拖出面板区域：本次拖放取消（不再接受；用户可拖回重新开始）
        log.debug("dragLeave：拖出面板区域，本次拖放取消")
        self._drag_state = "canceled"
        self._set_drop_hover(False)
        self._show_drop_hint(False)

    def dropEvent(self, event) -> None:
        self._set_drop_hover(False)
        self._show_drop_hint(False)
        self._drag_state = None
        md = event.mimeData()
        raw = RawPayload(
            files=[u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md.hasUrls() else [],
            text=md.text() if md.hasText() else None,
            html=md.html() if md.hasHtml() else None,
            image_bytes=ole.image_to_png_bytes(md.imageData()) if md.hasImage() else None,
        )
        entries = parse_payload(raw)
        log.debug("drop: files=%s hasText=%s entries=%d",
                  raw.files, bool(raw.text), len(entries))
        if not entries:
            self.show_toast(STR["mime_unsupported"], duration=2400)
            event.ignore()
            return
        event.acceptProposedAction()
        self.request_collect.emit(entries, "drag")

    request_collect = Signal(list, str)  # (RawEntry 列表, via)

    def _set_drop_hover(self, on: bool) -> None:
        self._surface.setProperty("dropHover", "true" if on else "false")
        style = self._surface.style()
        style.unpolish(self._surface)
        style.polish(self._surface)

    def _show_drop_hint(self, on: bool) -> None:
        if on:
            self._drop_hint.show()
            self._drop_hint.raise_()
        else:
            self._drop_hint.hide()

    # ================= Toast / 撤销 =================
    def show_toast(self, text: str, *, with_undo: bool = False, undo_cb=None, duration: int | None = None) -> None:
        self._undo_cb = undo_cb
        self._toast.show_message(text, with_undo=with_undo and undo_cb is not None, duration=duration)

    def after_drop_feedback(self, text: str, undo_cb) -> None:
        """存入成功反馈：提示 + 撤销 + 按设置自动收起。"""
        self.show_toast(text, with_undo=undo_cb is not None, undo_cb=undo_cb, duration=DROP_TOAST_MS)
        self._request_auto_hide()

    def _on_undo(self) -> None:
        cb = self._undo_cb
        self._undo_cb = None
        self._toast.cancel()
        if cb:
            cb()
        self.notify_list_changed()

    # ================= 会话看门狗（原“空闲监视”） =================
    def _on_idle(self) -> None:
        """呼出后保持“等待投放”会话：任何面板活动（焦点在面板/光标悬停/左键
        按住拖拽/拖放悬停/提示展示中）都刷新计时；持续无活动超过
        SESSION_TIMEOUT_MS 才自动收起。存入后走 after_drop 的自动收起。"""
        if not self.isVisible() or self.pinned:
            return
        active = (
            self._toast.isVisible()
            or QApplication.focusWindow() is self.windowHandle()
            or self.rect().contains(self.mapFromGlobal(QCursor.pos()))
            or dragstate.left_button_down()
            or self._drag_state == "over"
        )
        now = _now_ms()
        if active:
            self._last_active_ms = now
            return
        if now - self._last_active_ms > SESSION_TIMEOUT_MS:
            log.debug("会话超时（%dms 无活动），自动收起", SESSION_TIMEOUT_MS)
            self.hide_panel()

    # ================= 全局事件过滤 =================
    def eventFilter(self, obj, event) -> bool:
        # 焦点转移到其它应用：只更新“前台应用”上下文（作来源/发送目标），
        # 不收起——面板保持“等待投放”会话，由看门狗超时/热键/存入收起
        if obj is self and event.type() == QEvent.Type.WindowDeactivate:
            if QApplication.activePopupWidget() is None and QApplication.activeModalWidget() is None:
                self._remember_deactivated_app()
        return super().eventFilter(obj, event)


class _Stack(QWidget):
    """极简页面堆叠。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)

    def add_widget(self, w: QWidget) -> None:
        self._pages.append(w)
        self._lay.addWidget(w)
        w.hide()

    def set_page(self, index: int) -> None:
        for i, w in enumerate(self._pages):
            w.setVisible(i == index)


def _system_reduce_motion() -> bool:
    from transstation.resources.style import system_reduce_motion

    return system_reduce_motion()


def _svg_pixmap_scaled(name: str, color: str, width: int) -> QPixmap:
    renderer = QSvgRenderer(svg_for(name, color))
    size = renderer.defaultSize()
    h = round(size.height() * width / max(size.width(), 1)) if size.isValid() else round(width * 0.55)
    px = QPixmap(width, h)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p, QRect(0, 0, width, h))
    p.end()
    return px
