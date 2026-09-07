"""应用装配与业务编排：托盘、单实例、全局热键、面板操作（打开/复制/发送/拖出/菜单）。

数据流：UI(panel) 只发信号，动作统一收敛在本类，便于复用与记录。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from transstation import __version__, paths
from transstation.core import winutil
from transstation.core.hotkey import HotkeyManager
from transstation.core.mirror import cleanup_item_files, write_image_mirror, write_text_mirror
from transstation.olednd import payload as ole
from transstation.resources.strings_zh import STR
from transstation.resources.style import icon, icon_pixmap
from transstation.resources.tokens import COLORS
from transstation.store.backups import backup_if_due, copy_tree_verified, make_backup
from transstation.store.db import Item, Store
from transstation.store.settings import Settings
from transstation.ui.dialogs import ConfirmDialog, ContentDialog, NotesDialog
from transstation.ui.panel import Panel
from transstation.ui.recycle_dlg import RecycleDialog
from transstation.ui.settings_dlg import SettingsDialog

log = logging.getLogger(__name__)

ACTIONS = ("open", "drag_out", "copy", "send_to")


class App(QObject):
    """应用控制器：持有 store/settings/panel/tray/hotkey 并编排全部动作。"""

    def __init__(self, app: QApplication, *, data_dir_override: str | None = None):
        super().__init__(app)
        self._app = app
        self._running = True   # 第二实例时置 False
        self._smoke = bool(os.environ.get("TRANS_SMOKE"))
        if data_dir_override:
            paths.override_data_dir(Path(data_dir_override))  # 仅本进程，不写绑定文件
        dirs = paths.ensure_dirs()
        self._dirs = dirs

        log_file = dirs["logs"] / "transstation.log"
        _setup_file_logger(log_file)

        self.settings = Settings(dirs["root"] / "settings.json")
        self.store = Store(dirs["db"] / "transstation.db")
        self._hotkey_mgr = HotkeyManager(self)
        self.panel: Panel | None = None
        self._tray: QSystemTrayIcon | None = None
        self._server = None
        self._settings_dlg: SettingsDialog | None = None

    # ================= 生命周期 =================
    def start(self) -> None:
        # 过期回收站清理
        self._purge_expired_at_startup()
        # 每日备份（今天未备份则补）
        try:
            backup_if_due(self._dirs["root"], keep=int(self.settings.get("backup_keep")))
        except Exception as e:
            log.warning("每日备份失败: %s", e)

        self.panel = Panel(self.store, self.settings, hotkey_text=self.settings.get("hotkey"))
        self._wire_panel(self.panel)

        if os.environ.get("TRANS_LIVE"):
            # 真机快速自检：完整装配（含热键探测），不弹面板不驻留，2.5s 后退出
            log.info("TRANS_LIVE 自检模式")
            self._build_tray()
            err = self._register_hotkey(self.settings.get("hotkey"), notify_error=False)
            log.info("热键探测 Ctrl+Alt+T 结果: %s", err or "注册成功（随后释放）")
            self._hotkey_mgr.unregister_all()
            self._tray.hide()
            QTimer.singleShot(400, lambda: self._app.exit(0))
            return

        self._build_tray()
        if not self._smoke:
            if not self._acquire_single_instance():
                return  # 已有实例：唤醒后退出（exec 立即返回）
            self._register_hotkey(self.settings.get("hotkey"), notify_error=True)

        if self._smoke:
            self._run_smoke()
        else:
            log.info("TransStation v%s 启动完成，数据目录: %s", __version__, self._dirs["root"])

    def shutdown(self) -> None:
        self._hotkey_mgr.unregister_all()
        try:
            if self._tray is not None:
                self._tray.hide()
        except Exception:
            pass
        try:
            self.store.close()
        except Exception:
            pass
        log.info("已退出")

    # ---------- 启动杂项 ----------
    def _purge_expired_at_startup(self) -> None:
        try:
            from transstation.resources.tokens import LIMITS

            purged = self.store.purge_expired(days=LIMITS["recycle_days"])
            for it in purged:
                cleanup_item_files(it)
            if purged:
                log.info("启动清理过期回收站条目 %d 条", len(purged))
        except Exception as e:
            log.warning("回收站清理失败: %s", e)

    def _wire_panel(self, panel: Panel) -> None:
        panel.request_open.connect(self.open_item)
        panel.request_menu.connect(self.show_context_menu)
        panel.request_drag.connect(self.drag_out_item)
        panel.request_clipboard_add.connect(self.collect_from_clipboard)
        panel.request_settings.connect(self.open_settings)
        panel.request_collect.connect(self.collect_entries)
        panel.hidden_manually.connect(lambda: None)

    def _build_tray(self) -> None:
        tray = QSystemTrayIcon(self._app)
        tray.setIcon(icon("logo", COLORS["accent"], 16))
        self._update_tray_tooltip()
        menu = QMenu()
        act_show = QAction(STR["tray_show"], menu)
        act_show.triggered.connect(lambda: self.panel.show_panel(from_hotkey=False))
        act_report = QAction(STR["tray_report"], menu)
        act_report.setEnabled(False)
        act_report.setToolTip(STR["report_disabled"])
        act_settings = QAction(STR["tray_settings"], menu)
        act_settings.triggered.connect(self.open_settings)
        act_data = QAction(STR["tray_open_data"], menu)
        act_data.triggered.connect(self.open_data_dir)
        act_recycle = QAction(STR["recycle_title"], menu)
        act_recycle.triggered.connect(self.open_recycle)
        act_quit = QAction(STR["tray_quit"], menu)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_report)
        menu.addAction(act_settings)
        menu.addAction(act_data)
        menu.addAction(act_recycle)
        menu.addSeparator()
        menu.addAction(act_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: reason == QSystemTrayIcon.ActivationReason.DoubleClick
            and self.panel.show_panel(from_hotkey=False)
        )
        tray.show()
        self._tray = tray

    def _update_tray_tooltip(self) -> None:
        if self._tray is not None:
            self._tray.setToolTip(
                STR["tray_tooltip"].format(hotkey=self.settings.get("hotkey"))
            )

    def _quit(self) -> None:
        if QMessageBox.question(
            None, STR["app_title"], STR["tray_quit_confirm"],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.shutdown()
            self._app.quit()

    # ================= 单实例 =================
    def _acquire_single_instance(self) -> bool:
        """互斥锁（QLockFile，Windows 上 QLocalServer 同名可并存，不能当锁用）。
        加锁失败视为已有实例：经命名管道唤醒其面板后退出本进程。"""
        from PySide6.QtCore import QLockFile
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        lock_path = self._dirs["root"] / "transstation.lock"
        lock = QLockFile(str(lock_path))
        if lock.tryLock(100):
            self._lock = lock
            # 唤醒通道（listen 失败无妨：锁已说明我们是唯一实例）
            name = "TransStation-" + _short_id(str(self._dirs["root"]))
            server = QLocalServer(self)
            server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
            server.listen(name)
            server.newConnection.connect(self._on_peer_connected)
            self._server = server
            return True
        # 第二实例：唤醒并退出（由主进程检查 _running 决定不进入事件循环）
        try:
            from PySide6.QtNetwork import QAbstractSocket, QLocalSocket

            sock = QLocalSocket(self)
            sock.connectToServer("TransStation-" + _short_id(str(self._dirs["root"])))
            if sock.waitForConnected(800):
                sock.write(b"show")
                sock.flush()
                sock.waitForBytesWritten(300)
                sock.disconnectFromServer()
        except Exception as e:
            log.warning("唤醒已有实例失败: %s", e)
        log.info("已存在运行实例，唤醒后退出")
        self._running = False
        return False

    def _on_peer_connected(self) -> None:
        if self._server is None:
            return
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda: self._on_peer_message(conn))
        conn.disconnected.connect(conn.deleteLater)

    def _on_peer_message(self, conn) -> None:
        _ = conn.readAll().data()
        log.info("收到第二实例唤醒请求，显示面板")
        if self.panel is not None:
            self.panel.show_panel(from_hotkey=False)

    # ================= 热键 =================
    def _register_hotkey(self, seq: str, notify_error: bool = False) -> str | None:
        err = self._hotkey_mgr.register(seq)
        if err is None:
            self._hotkey_mgr.activated.connect(self._on_hotkey, type=Qt.ConnectionType.UniqueConnection)
            self._update_tray_tooltip()
            return None
        log.warning("热键注册失败 %s: %s", seq, err)
        if notify_error and self._tray is not None:
            self._tray.showMessage(
                STR["app_title"],
                STR["tray_hotkey_error"].format(msg=err),
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )
        return err

    def _on_hotkey(self, seq: str) -> None:
        log.debug("收到全局热键: %s", seq)
        if self.panel is not None:
            self.panel.show_panel()

    # ================= 面板操作实现 =================
    def _ctx_source(self):
        """取“前台/最近外部应用”作为来源或发送目标；忽略清单命中返回 None。"""
        ctx = self.panel.context_app() if self.panel else None
        if ctx is None or winutil.is_same_process(ctx.pid):
            return None
        if ctx.matched_by(self.settings.get("ignore_apps") or []):
            return None
        return ctx

    def collect_entries(self, entries: list, via: str) -> None:
        """统一入口：拖入 / 剪贴板添加 → 入库 + 镜像 + 记录 + 反馈。"""
        ctx = self._ctx_source()
        src_app = ctx.name if ctx else ""
        src_win = ctx.title if ctx else ""
        action = "collect_drag" if via == "drag" else "collect_clipboard"
        ids: list[int] = []
        titles: list[str] = []
        mirror_text = bool(self.settings.get("text_mirror"))
        try:
            for e in entries:
                item_id = self._store_entry(e, src_app, src_win, mirror_text)
                if item_id:
                    ids.append(item_id)
                    titles.append(e.title)
                    if ctx is not None:  # 忽略清单命中则不做任何记录
                        self.store.log_usage(item_id, action, src_app=src_app, src_window=src_win)
            self._on_collected(ids, titles, action)
        except Exception as exc:
            log.exception("存入失败")
            self.panel.show_toast(f"存入失败：{exc}", duration=4000)

    def _store_entry(self, e, src_app: str, src_win: str, mirror_text: bool) -> int | None:
        kind, title, path_, url, flags, image_bytes = (
            e.kind, e.title, e.path, e.url, e.flags, e.image_bytes,
        )
        if kind == "image" and image_bytes:
            # 位图来源：先插记录占位 id，再写镜像文件并回填路径
            item_id = self.store.create(
                "image", title=title, src_app=src_app, src_window=src_win,
            )
            p = write_image_mirror(item_id, image_bytes)
            self.store.update(item_id, image_file=str(p), path=str(p), title=title)
            return item_id
        item_id = self.store.create(
            kind, title=title, content=e.content, path=path_, url=url,
            flags=flags, src_app=src_app, src_window=src_win,
        )
        if kind == "text" and mirror_text:
            try:
                write_text_mirror(item_id, e.content)
            except OSError as exc:
                log.warning("文本镜像写入失败: %s", exc)
        return item_id

    def _on_collected(self, ids: list[int], titles: list[str], action: str) -> None:
        n = len(ids)
        if n == 0:
            self.panel.show_toast(STR["toast_clipboard_empty"], duration=2600)
            return
        if n == 1:
            text = STR["toast_stored_one"].format(title=(titles[0] or "")[:40])
        else:
            text = STR["toast_stored"].format(n=n)
        undo_cb = (lambda: self._undo_store(ids)) if action.startswith("collect") else None
        self.panel.notify_list_changed()
        if action == "collect_drag":
            self.panel.after_drop_feedback(text, undo_cb)
        else:
            self.panel.show_toast(text, with_undo=undo_cb is not None, undo_cb=undo_cb, duration=3600)

    def _undo_store(self, ids: list[int]) -> None:
        try:
            purged = self.store.hard_delete(ids)
            for it in purged:
                cleanup_item_files(it)
        except Exception as e:
            log.warning("撤销存入失败: %s", e)
        self.panel.notify_list_changed()

    # ================= 剪贴板收集 =================
    def collect_from_clipboard(self) -> None:
        raw = ole.read_clipboard_payload()
        if raw is None:
            self.panel.show_toast(STR["toast_clipboard_empty"], duration=2600)
            return
        from transstation.core.kinds import parse_payload

        entries = parse_payload(raw)
        if not entries:
            self.panel.show_toast(STR["toast_clipboard_empty"], duration=2600)
            return
        self.collect_entries(entries, via="clipboard")

    # ================= 打开 / 取用 =================
    def open_item(self, item: Item) -> None:
        if item.kind == "text":
            self.view_text(item)
            return
        if item.kind in ("file", "image"):
            target = item.path if (item.path and Path(item.path).exists()) else (
                item.image_file if (item.kind == "image" and item.image_file and Path(item.image_file).exists()) else None
            )
            if not target:
                self.panel.show_toast(
                    STR["toast_not_found"].format(path=item.path or item.image_file or "?"), duration=3600
                )
                return
            os.startfile(target)
            self._log_use_later(item, "open", after_ms=1200)
        elif item.kind == "link":
            url = item.url or item.content
            if url:
                webbrowser.open(url)
                self._log_use_later(item, "open", after_ms=1500)

    def view_text(self, item: Item) -> None:
        dlg = ContentDialog(item.title or STR["kind_text"], item.content, self.panel)
        if dlg.exec() == ContentDialog.DialogCode.Accepted:
            content = dlg.result_content()
            self.store.update(item.id, content=content, title=_title_from_text(content))
            self.panel.notify_item_changed(item.id)
        self.store.log_usage(item.id, "view")

    def copy_item(self, item: Item) -> None:
        mime = ole.mime_for_item(item)
        if not mime.formats():
            self.panel.show_toast(
                STR["toast_not_found"].format(path=item.path or "?"), duration=3200
            )
            return
        ole.set_clipboard(mime)
        what = {
            "file": STR["kind_file"], "image": STR["kind_image"],
            "link": STR["kind_link"], "text": STR["kind_text"],
        }.get(item.kind, "")
        self.panel.show_toast(STR["toast_copied"].format(what=what), duration=2000)
        self._log_use(item, "copy")

    def copy_path(self, item: Item) -> None:
        p = item.path or item.image_file or item.url or item.content
        if not p:
            return
        from PySide6.QtCore import QMimeData

        m = QMimeData()
        m.setText(p)
        ole.set_clipboard(m)
        self.panel.show_toast(STR["toast_copied_path"], duration=2000)

    def send_to_foreground(self, item: Item) -> None:
        ctx = self.panel.context_app() if self.panel else None
        if ctx is None or winutil.is_same_process(ctx.pid) or not winutil.is_window_alive(ctx.hwnd):
            self.panel.show_toast(STR["toast_send_fail"], duration=2800)
            return
        mime = ole.mime_for_item(item)
        if not mime.formats():
            self.panel.show_toast(STR["toast_not_found"].format(path=item.path or "?"), duration=3200)
            return
        ole.set_clipboard(mime)
        self._log_use(item, "send_to", dst=ctx)
        if self.settings.get("send_auto_paste"):
            winutil.activate_and_paste(ctx.hwnd)
            self.panel.show_toast(STR["toast_sent_pasted"].format(app=ctx.name), duration=2400)
        else:
            self.panel.show_toast(
                STR["toast_sent_clipboard"].format(app=ctx.name), duration=2800
            )

    def drag_out_item(self, item: Item, global_pos) -> None:
        mime = ole.mime_for_item(item)
        if not mime.formats():
            self.panel.show_toast(
                STR["toast_not_found"].format(path=item.path or "?"), duration=3200
            )
            return
        from PySide6.QtGui import QDrag

        drag = QDrag(self.panel)
        drag.setMimeData(mime)
        result = drag.exec(Qt.DropAction.CopyAction)
        if result != Qt.DropAction.CopyAction:
            return
        # 去向：以松手点所在窗口为准（注意 DPI：Qt 逻辑坐标 → 物理像素）
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos)
        dpr = screen.devicePixelRatio() if screen else 1.0
        dst = winutil.window_at_point(int(pos.x() * dpr), int(pos.y() * dpr))
        if dst is not None and not winutil.is_same_process(dst.pid):
            self._log_use(item, "drag_out", dst=dst)

    # ---------- 记录 ----------
    def _log_use(self, item: Item, action: str, dst=None) -> None:
        try:
            dst_name = dst.name if dst else ""
            dst_win = dst.title if dst else ""
            self.store.log_usage(item.id, action, dst_app=dst_name, dst_window=dst_win)
            self.panel.notify_item_changed(item.id)
        except Exception as e:
            log.warning("使用记录失败: %s", e)

    def _log_use_later(self, item: Item, action: str, after_ms: int) -> None:
        """打开外部程序后延迟探测前台应用并记录去向；探测失败也留一条去向为空的记录。"""

        def tick():
            app = winutil.foreground_app()
            dst = app if (app is not None and not winutil.is_same_process(app.pid)) else None
            self._log_use(item, action, dst=dst)

        QTimer.singleShot(after_ms, tick)

    # ================= 文件操作 =================
    def show_in_explorer(self, item: Item) -> None:
        p = item.path or item.image_file
        if not (p and Path(p).exists()):
            self.panel.show_toast(STR["toast_not_found"].format(path=p or "?"), duration=3200)
            return
        try:
            subprocess.Popen(["explorer", "/select,", str(Path(p).resolve())])
        except OSError as e:
            log.warning("explorer 调用失败: %s", e)

    def toggle_pin(self, item: Item) -> None:
        self.store.update(item.id, pinned=not item.pinned)
        self.panel.notify_item_changed(item.id)

    def edit_notes(self, item: Item) -> None:
        dlg = NotesDialog(item.title or STR["kind_text"], item.notes, self.panel)
        if dlg.exec() == NotesDialog.DialogCode.Accepted:
            self.store.update(item.id, notes=dlg.result_notes())
            self.panel.notify_item_changed(item.id)

    def change_kind(self, item: Item, new_kind: str) -> None:
        from transstation.store.db import KINDS

        if new_kind not in KINDS:
            return
        self.store.update(item.id, kind=new_kind)
        self.panel.notify_item_changed(item.id)

    def delete_item(self, item: Item) -> None:
        self.store.soft_delete([item.id])
        self.panel.notify_list_changed()
        self.panel.show_toast(
            STR["toast_deleted"], with_undo=True,
            undo_cb=lambda: self._restore_ids([item.id]),
            duration=3200,
        )

    def _restore_ids(self, ids: list[int]) -> None:
        self.store.restore(ids)
        self.panel.notify_list_changed()

    # ================= 右键菜单 =================
    def show_context_menu(self, item: Item, global_pos) -> None:
        menu = QMenu(self.panel)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        kind = item.kind

        def add(text: str, cb, *, enabled: bool = True):
            a = menu.addAction(text)
            a.setEnabled(enabled)
            if enabled:
                a.triggered.connect(lambda _=False, f=cb: f())
            return a

        add(STR["menu_open"], lambda: self.open_item(item),
            enabled=not (kind == "file" and not _exists(item.path)))
        menu.addSeparator()
        add(STR["menu_copy"], lambda: self.copy_item(item), enabled=_copiable(item))
        add(STR["menu_copy_path"], lambda: self.copy_path(item),
            enabled=bool(item.path or item.image_file or item.url))
        add(STR["menu_send_foreground"], lambda: self.send_to_foreground(item), enabled=_copiable(item))
        if kind in ("file", "image"):
            menu.addSeparator()
            add(STR["menu_show_in_explorer"], lambda: self.show_in_explorer(item),
                enabled=_exists(item.path or item.image_file))
        if kind == "text":
            add(STR["menu_view_text"], lambda: self.view_text(item))
        menu.addSeparator()
        type_menu = menu.addMenu(STR["menu_change_type"])
        from transstation.store.db import KINDS

        for k in KINDS:
            label = {"file": STR["kind_file"], "image": STR["kind_image"],
                     "link": STR["kind_link"], "text": STR["kind_text"]}[k]
            a = type_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(k == kind)
            a.triggered.connect(lambda _=False, nk=k: self.change_kind(item, nk))
        add(STR["menu_edit_notes"], lambda: self.edit_notes(item))
        add(STR["menu_unpin"] if item.pinned else STR["menu_pin"],
           lambda: self.toggle_pin(item))
        menu.addSeparator()
        add(STR["menu_delete"], lambda: self.delete_item(item))
        menu.exec(global_pos)

    # ================= 设置 / 数据目录 =================
    def open_settings(self) -> None:
        if self._settings_dlg is not None and self._settings_dlg.isVisible():
            self._settings_dlg.raise_()
            return
        dlg = SettingsDialog(self.settings, app_ops=self, parent=self.panel)
        self._settings_dlg = dlg
        dlg.finished.connect(lambda _: setattr(self, "_settings_dlg", None))
        dlg.open()

    def apply(self, values: dict) -> str | None:
        """设置窗口点“确定”后的应用入口；返回错误信息则中止。"""
        # 1) 快捷键：先注册新键，失败则中止（保留原键）
        new_hotkey = values.get("hotkey")
        if new_hotkey and new_hotkey != self.settings.get("hotkey"):
            err = self._hotkey_mgr.register(new_hotkey)
            if err:
                return STR["tray_hotkey_error"].format(msg=err)
            self._hotkey_mgr.unregister(self.settings.get("hotkey"))
            self.settings.set("hotkey", new_hotkey)
        # 2) 数据目录迁移（单独处理）
        chosen = (values.pop("data_dir") or "").strip()
        if chosen:
            current = paths.data_dir()
            new_dir = Path(chosen).expanduser()
            try:
                if new_dir.resolve() != current.resolve():
                    err = self._migrate_data_dir(new_dir)
                    if err:
                        return err
            except Exception as e:
                return f"数据目录迁移失败：{e}"
        # 3) 其余键
        for key, val in values.items():
            self.settings.set(key, val)
        self.settings.save()
        self._after_settings_applied()
        return None

    def _after_settings_applied(self) -> None:
        self._update_tray_tooltip()
        if self.panel is not None:
            self.panel.save_geometry()
            self.panel.reload()

    def _migrate_data_dir(self, new_dir: Path) -> str | None:
        old = paths.data_dir()
        if new_dir.resolve() in [old.resolve(), old.resolve().parent]:
            return "目标目录无效"
        if new_dir.exists() and any(new_dir.iterdir()):
            return "目标目录非空，请选择空目录"
        renamed = False
        try:
            try:
                old.rename(new_dir)          # 同卷：目录改名，数据文件原地不动
                renamed = True
            except OSError:
                # 跨卷：先关库，再复制校验删除源
                self.store.close()
                copy_tree_verified(old, new_dir)
            paths.set_data_dir(new_dir)
            self._dirs = paths.ensure_dirs()
            if not renamed:
                self.store = Store(self._dirs["db"] / "transstation.db")
            if self.panel is not None:
                self.panel._store = self.store
            # 设置文件随目录搬走，重读
            self.settings = Settings(self._dirs["root"] / "settings.json")
            self.settings.load()
            return None
        except Exception as e:
            log.exception("数据目录迁移失败")
            if renamed:
                return f"迁移后初始化失败：{e}"
            try:
                self.store = Store(old / "db" / "transstation.db")
                if self.panel is not None:
                    self.panel._store = self.store
            except Exception:
                pass
            return str(e)

    def backup_now(self) -> str | None:
        try:
            made = make_backup(
                self._dirs["root"], self._dirs["backups"],
                keep=int(self.settings.get("backup_keep")),
            )
            if made is None:
                QMessageBox.information(None, STR["app_title"], "今天已备份过")
            else:
                QMessageBox.information(
                    None, STR["app_title"], STR["settings_backup_done"].format(path=made)
                )
            return None
        except Exception as e:
            return STR["settings_backup_fail"].format(msg=e)

    def open_data_dir(self) -> None:
        os.startfile(str(self._dirs["root"]))

    def open_recycle(self) -> None:
        dlg = RecycleDialog(self.store, self.settings, parent=self.panel)
        dlg.finished.connect(lambda _: self.panel.notify_list_changed())
        dlg.exec()

    # ================= 冒烟 =================
    def _run_smoke(self) -> None:
        """自动化自检：面板构建/刷新/存入/撤销/查询。"""
        from transstation.core.kinds import RawEntry

        panel = self.panel
        print("[smoke] 基础自检开始…")
        assert panel is not None
        # 空数据目录下：面板构建并显示一次
        panel.show_panel()
        QTimer.singleShot(200, self._smoke_step2)

    def _smoke_step2(self) -> None:
        from transstation.core.kinds import RawEntry

        # 模拟存入：文本 + 链接 + 文件占位
        src = None
        ids: list[int] = []
        for e in [
            RawEntry("text", title="测试文本", content="这是来自冒烟测试的一段文本内容"),
            RawEntry("link", title="示例链接", url="https://example.com/", content="https://example.com/"),
            RawEntry("file", title="测试文件.txt", path=str(Path(self._dirs["root"]) / "no-such-file.txt")),
        ]:
            ids.append(self._store_entry(e, "smoke", "", False))
        print(f"[smoke] 已插入 {len(ids)} 条")
        total = self.store.count_items(deleted=False)
        assert total == 3, f"预期 3 条, 实际 {total}"
        # 软删+恢复
        self.store.soft_delete([ids[0]])
        assert self.store.count_items(deleted=False) == 2
        self.store.restore([ids[0]])
        assert self.store.count_items(deleted=False) == 3
        # 搜索
        found = self.store.list_items(search="冒烟")
        assert len(found) == 1
        # 面板刷新 + 真实绘制一遍（触发 delegate paint / 缩略图路径）
        self.panel.reload()
        self.panel.grab()
        # 置顶/备注切换的行刷新
        self.store.update(ids[1], pinned=True, notes="冒烟备注")
        self.panel.notify_item_changed(ids[1])
        self.panel.grab()
        self._assert_render_plausible()
        # 浅色调色板断言（防深色系统主题回归）
        pal = self._app.palette()
        win_color = pal.color(pal.ColorRole.Window)
        assert (win_color.red() + win_color.green() + win_color.blue()) / 3 > 180, \
            f"调色板 Window 非浅色: {win_color.name()}"
        # 撤销（物理删除）
        self._undo_store(ids)
        assert self.store.count_items(deleted=False) == 0
        self.panel.reload()
        self.panel.grab()
        print("[smoke] 数据层 + 面板绘制断言通过")
        QTimer.singleShot(100, self._smoke_done)

    def _assert_render_plausible(self) -> None:
        """无目视条件下的渲染合理性自检：像素统计 + 布局边界。"""
        img = self.panel.grab().toImage()
        w, h = img.width(), img.height()
        assert w > 300 and h > 400, f"面板尺寸异常 {w}x{h}"
        nontrans = 0
        colors = set()
        step = 4
        for y in range(0, h, step):
            for x in range(0, w, step):
                c = img.pixelColor(x, y)
                if c.alpha() > 8:
                    nontrans += 1
                    colors.add((c.red() // 48, c.green() // 48, c.blue() // 48))
        ratio = nontrans / max(1, (w // step) * (h // step))
        print(f"[smoke] 渲染统计: {w}x{h} 非透明占比={ratio:.2f} 颜色分桶={len(colors)}")
        assert ratio > 0.5, f"非透明像素占比过低 {ratio:.2f}（疑似整窗未绘制）"
        assert len(colors) >= 4, f"颜色分桶过少 {len(colors)}（疑似空白面板）"
        # 布局边界：子控件不越出表面
        from PySide6.QtWidgets import QWidget

        surface = self.panel._surface
        sr = surface.rect()
        for child in surface.findChildren(QWidget):
            if child.isVisible() and child.parentWidget() is surface:
                assert sr.adjusted(-2, -2, 2, 2).contains(child.geometry()), \
                    f"控件越界 {child}"
        print(f"[smoke] 渲染像素自检通过 {w}x{h} ratio={ratio:.2f} colors={len(colors)}")

    def _smoke_done(self) -> None:
        print("[smoke] ALL PASS")
        self._app.exit(0)


def _setup_file_logger(path: Path) -> None:
    from logging.handlers import RotatingFileHandler

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.DEBUG if os.environ.get("TRANS_DEBUG") else logging.INFO)
        root.addHandler(handler)
    except OSError:
        pass


def _short_id(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:10]


def _exists(p: str) -> bool:
    return bool(p) and Path(p).exists()


def _copiable(item: Item) -> bool:
    if item.kind in ("file", "image"):
        return _exists(item.path) or _exists(item.image_file)
    return bool(item.kind in ("link", "text") and (item.content or item.url))


def _title_from_text(content: str) -> str:
    line = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
    return line[:60]
