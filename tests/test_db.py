"""Store / 回收站 / 使用记录测试。"""
from datetime import datetime, timedelta

import pytest


def _mk(store, kind="text", title="t", **kw):
    return store.create(kind, title=title, **kw)


def test_create_and_get(store):
    iid = _mk(store, title="你好", content="内容", src_app="Chrome")
    item = store.get(iid)
    assert item.id == iid
    assert item.title == "你好"
    assert item.src_app == "Chrome"
    assert item.created_at
    assert store.count_items() == 1


def test_kind_filter(store):
    _mk(store, "file", path=r"C:\a.txt")
    _mk(store, "link", url="https://x.com")
    _mk(store, "text")
    assert store.count_items(kind="file") == 1
    assert store.count_items(kind="link") == 1
    assert store.count_items(kind="all") == 3
    assert len(store.list_items(kind="text")) == 1


def test_search_covers_title_content_notes_url(store):
    a = _mk(store, title="季度预算表", content="")
    b = _mk(store, "link", url="https://internal.example.com/wiki", title="内部维基")
    c = _mk(store, title="xx", notes="标签：重要", content="随便")
    assert {x.id for x in store.list_items(search="预算")} == {a}
    assert {x.id for x in store.list_items(search="internal")} == {b}
    assert {x.id for x in store.list_items(search="重要")} == {c}
    # % 和 _ 需转义
    d = _mk(store, title="100%_完成")
    assert {x.id for x in store.list_items(search="%_")} == {d}


def test_ordering_pinned_first(store):
    newer = _mk(store, title="新")
    older = _mk(store, title="旧")
    store.update(older, pinned=True)
    rows = store.list_items()
    assert rows[0].id == older  # 置顶优先，其次 id 倒序
    assert rows[1].id == newer


def test_soft_delete_restore_purge(store):
    a, b, c = _mk(store), _mk(store), _mk(store)
    assert store.soft_delete([a, b]) == 2
    assert store.count_items(deleted=False) == 1
    assert len(store.list_deleted()) == 2
    assert store.restore([a]) == 1
    assert store.count_items(deleted=False) == 2
    # 过期清理
    store.soft_delete([a])
    ts = (datetime.now() - timedelta(days=31)).isoformat(timespec="seconds")
    store.conn.execute("UPDATE items SET deleted_at=? WHERE id=?", (ts, a))
    store.conn.commit()
    purged = store.purge_expired(days=30)
    assert [x.id for x in purged] == [a]
    assert store.get(a) is None


def test_usage_log_and_weekly(store):
    a = _mk(store)
    store.log_usage(a, "collect_drag", src_app="Explorer")
    store.log_usage(a, "open", dst_app="Word")
    store.log_usage(a, "drag_out", dst_app="微信")
    assert store.weekly_use_count() == 2  # collect 不算“使用”
    item = store.get(a)
    assert item.use_count == 2
    assert store.last_usage(a) is not None


def test_update_fields(store):
    a = _mk(store, title="x")
    store.update(a, pinned=True, notes="n1")
    item = store.get(a)
    assert item.pinned is True
    assert item.notes == "n1"


def test_hard_delete_removes_usage(store):
    a = _mk(store)
    store.log_usage(a, "open")
    rows = store.hard_delete([a])
    assert len(rows) == 1
    assert store.count_items() == 0
    assert store.conn.execute("SELECT COUNT(*) c FROM usage_log").fetchone()["c"] == 0
