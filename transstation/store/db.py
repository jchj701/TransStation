"""SQLite 存储层：schema 版本化、条目 CRUD、软删除回收站、使用记录与统计。

时间一律存本地时间字符串 ISO(YYYY-MM-DDTHH:MM:SS)，便于阅读与排序。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

KINDS = ("file", "image", "link", "text")

# 取用类动作（区别于收集）
USE_ACTIONS = ("open", "drag_out", "copy", "send_to", "view")
COLLECT_ACTIONS = ("collect_drag", "collect_clipboard")

_COLUMNS = (
    "id", "kind", "title", "content", "path", "url", "image_file",
    "notes", "pinned", "flags", "src_app", "src_window",
    "created_at", "updated_at", "last_used_at", "use_count",
    "deleted_at", "deleted_reason",
)


@dataclass
class Item:
    kind: str
    title: str = ""
    content: str = ""
    path: str = ""
    url: str = ""
    image_file: str = ""
    notes: str = ""
    pinned: bool = False
    flags: str = ""
    src_app: str = ""
    src_window: str = ""
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""
    use_count: int = 0
    deleted_at: str | None = None
    deleted_reason: str = ""

    @property
    def is_dir(self) -> bool:
        return "dir" in self.flags.split(",")

    @property
    def kind_display(self) -> str:
        return self.kind


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _e(s: str | None) -> str:
    """LIKE 转义。"""
    return (s or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Store:
    """单连接（主线程使用）；启用 WAL。"""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ---------- schema ----------
    def _migrate(self) -> None:
        cur = self.conn.execute("PRAGMA user_version")
        version = cur.fetchone()[0]
        if version < 1:
            # 全部幂等：进程重启/双实例短暂并发打开时不会炸
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('file','image','link','text')),
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    path TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    image_file TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    flags TEXT NOT NULL DEFAULT '',
                    src_app TEXT NOT NULL DEFAULT '',
                    src_window TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    deleted_reason TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_items_active ON items(deleted_at, pinned, id);
                CREATE INDEX IF NOT EXISTS idx_items_kind ON items(deleted_at, kind);
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER,
                    action TEXT NOT NULL,
                    src_app TEXT NOT NULL DEFAULT '',
                    src_window TEXT NOT NULL DEFAULT '',
                    dst_app TEXT NOT NULL DEFAULT '',
                    dst_window TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_usage_item ON usage_log(item_id);
                CREATE INDEX IF NOT EXISTS idx_usage_at ON usage_log(at);
                """
            )
            self.conn.execute("PRAGMA user_version = 1")
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- 基础 ----------
    def meta_get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> Item:
        d = {k: row[k] for k in row.keys()}
        d["pinned"] = bool(d["pinned"])
        return Item(**d)

    # ---------- 条目 CRUD ----------
    def create(
        self,
        kind: str,
        *,
        title: str = "",
        content: str = "",
        path: str = "",
        url: str = "",
        image_file: str = "",
        notes: str = "",
        pinned: bool = False,
        flags: str = "",
        src_app: str = "",
        src_window: str = "",
    ) -> int:
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO items(kind,title,content,path,url,image_file,notes,pinned,"
            "flags,src_app,src_window,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kind, title, content, path, url, image_file, notes,
             1 if pinned else 0, flags, src_app, src_window, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update(self, item_id: int, **fields) -> None:
        allowed = {
            "kind", "title", "content", "path", "url", "image_file",
            "notes", "pinned", "flags", "src_app", "src_window",
        }
        sets = [f"{k}=?" for k in fields if k in allowed]
        if not sets:
            return
        vals = [
            (1 if (v is True) else 0) if k == "pinned" else v
            for k, v in fields.items()
            if k in allowed
        ]
        vals.append(now_iso())
        self.conn.execute(
            f"UPDATE items SET {', '.join(sets)}, updated_at=? WHERE id=?",
            (*vals, item_id),
        )
        self.conn.commit()

    def get(self, item_id: int) -> Item | None:
        row = self.conn.execute(
            "SELECT * FROM items WHERE id=?", (item_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def get_active(self, item_id: int) -> Item | None:
        row = self.conn.execute(
            "SELECT * FROM items WHERE id=? AND deleted_at IS NULL", (item_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def touch_use(self, item_id: int) -> None:
        self.conn.execute(
            "UPDATE items SET last_used_at=?, use_count=use_count+1 WHERE id=?",
            (now_iso(), item_id),
        )
        self.conn.commit()

    # ---------- 查询 ----------
    def _list_where(self, kind, search, deleted) -> tuple[str, list]:
        where, args = [], []
        if deleted:
            where.append("deleted_at IS NOT NULL")
        else:
            where.append("deleted_at IS NULL")
        if kind and kind != "all":
            where.append("kind=?")
            args.append(kind)
        if search:
            like = f"%{_e(search)}%"
            where.append(
                "(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' "
                "OR notes LIKE ? ESCAPE '\\' OR url LIKE ? ESCAPE '\\')"
            )
            args += [like] * 4
        return " AND ".join(where), args

    def list_items(
        self,
        kind: str | None = None,
        search: str | None = None,
        deleted: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Item]:
        where, args = self._list_where(kind, search, deleted)
        sql = "SELECT * FROM items WHERE " + where
        sql += " ORDER BY pinned DESC, id DESC LIMIT ? OFFSET ?"
        rows = self.conn.execute(sql, (*args, limit, offset)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def count_items(
        self, kind: str | None = None, search: str | None = None, deleted: bool = False
    ) -> int:
        where, args = self._list_where(kind, search, deleted)
        row = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM items WHERE {where}", args
        ).fetchone()
        return int(row["n"])

    # ---------- 软删除与回收站 ----------
    def soft_delete(self, item_ids: list[int], reason: str = "user") -> int:
        if not item_ids:
            return 0
        ts = now_iso()
        cur = self.conn.executemany(
            "UPDATE items SET deleted_at=?, deleted_reason=? WHERE id=? AND deleted_at IS NULL",
            [(ts, reason, i) for i in item_ids],
        )
        self.conn.commit()
        return cur.rowcount

    def restore(self, item_ids: list[int]) -> int:
        if not item_ids:
            return 0
        cur = self.conn.executemany(
            "UPDATE items SET deleted_at=NULL, deleted_reason='' WHERE id=?",
            [(i,) for i in item_ids],
        )
        self.conn.commit()
        return cur.rowcount

    def list_deleted(self, limit: int = 300) -> list[Item]:
        return self.list_items(deleted=True, limit=limit, offset=0)

    def hard_delete(self, item_ids: list[int]) -> list[Item]:
        """物理删除并返回被删条目（调用方负责清理镜像文件）。"""
        if not item_ids:
            return []
        placeholders = ",".join("?" * len(item_ids))
        rows = self.conn.execute(
            f"SELECT * FROM items WHERE id IN ({placeholders})", item_ids
        ).fetchall()
        items = [self._row_to_item(r) for r in rows]
        self.conn.execute(
            f"DELETE FROM items WHERE id IN ({placeholders})", item_ids
        )
        self.conn.execute(
            f"DELETE FROM usage_log WHERE item_id IN ({placeholders})", item_ids
        )
        self.conn.commit()
        return items

    def purge_expired(self, days: int = 30) -> list[Item]:
        """物理清理过期回收站条目（返回被清理条目）。"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT id FROM items WHERE deleted_at IS NOT NULL AND deleted_at < ?",
            (cutoff,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        return self.hard_delete(ids) if ids else []

    # ---------- 使用记录 ----------
    def log_usage(
        self,
        item_id: int | None,
        action: str,
        *,
        src_app: str = "",
        src_window: str = "",
        dst_app: str = "",
        dst_window: str = "",
        note: str = "",
    ) -> None:
        self.conn.execute(
            "INSERT INTO usage_log(item_id,action,src_app,src_window,dst_app,dst_window,note,at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (item_id, action, src_app, src_window, dst_app, dst_window, note, now_iso()),
        )
        if item_id is not None and action in USE_ACTIONS:
            self.touch_use(item_id)
        self.conn.commit()

    def weekly_use_count(self) -> int:
        """本周取用次数（周一 00:00 起）。"""
        monday = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat(timespec="seconds")
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM usage_log WHERE at>=? AND action IN "
            + "(" + ",".join("?" * len(USE_ACTIONS)) + ")",
            (monday, *USE_ACTIONS),
        ).fetchone()
        return int(row["n"])

    def last_usage(self, item_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT at FROM usage_log WHERE item_id=? AND action IN "
            + "(" + ",".join("?" * len(USE_ACTIONS)) + ") "
            + "ORDER BY at DESC LIMIT 1",
            (item_id, *USE_ACTIONS),
        ).fetchone()
        return row["at"] if row else None

    def total_use_count(self, item_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM usage_log WHERE item_id=? AND action IN "
            + "(" + ",".join("?" * len(USE_ACTIONS)) + ")",
            (item_id, *USE_ACTIONS),
        ).fetchone()
        return int(row["n"])
