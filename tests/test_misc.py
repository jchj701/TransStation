"""备份/镜像/设置/时间工具测试。"""
import zipfile
from pathlib import Path


def test_make_backup_skips_when_duplicate(tmp_data_dir):
    from transstation.store.backups import make_backup

    (tmp_data_dir / "db").mkdir(exist_ok=True)
    (tmp_data_dir / "db" / "x.db").write_bytes(b"data")
    (tmp_data_dir / "images" / "1.png").write_bytes(b"img")
    backups = tmp_data_dir / "backups"
    first = make_backup(tmp_data_dir, backups, keep=3)
    assert first is not None and first.exists()
    # 同一天再次备份 → 跳过
    assert make_backup(tmp_data_dir, backups, keep=3) is None
    # zip 内含 db 与镜像，不含 backups 自身
    with zipfile.ZipFile(first) as zf:
        names = zf.namelist()
    assert "db/x.db" in names and "images/1.png" in names
    assert not any(n.startswith("backups/") for n in names)


def test_backup_prune_keeps_latest(tmp_data_dir):
    from transstation.store.backups import _prune

    backups = tmp_data_dir / "backups"
    backups.mkdir(exist_ok=True)
    for day in ("20260101", "20260102", "20260103", "20260104", "20260105"):
        (backups / f"backup-{day}.zip").write_bytes(b"x")
    _prune(backups, keep=3)
    remaining = sorted(p.name for p in backups.glob("backup-*.zip"))
    assert remaining == ["backup-20260103.zip", "backup-20260104.zip", "backup-20260105.zip"]


def test_copy_tree_verified_same_volume(tmp_data_dir):
    """同卷迁移走 rename。"""
    from transstation.store.backups import copy_tree_verified

    src = tmp_data_dir / "src"
    dst = tmp_data_dir / "dst"
    (src / "db").mkdir(parents=True)
    (src / "db" / "a.db").write_bytes(b"a")
    copy_tree_verified(src, dst)
    assert (dst / "db" / "a.db").read_bytes() == b"a"
    assert not src.exists()


def test_copy_tree_verified_refuses_nonempty(tmp_data_dir):
    from transstation.store.backups import copy_tree_verified

    src = tmp_data_dir / "src"
    dst = tmp_data_dir / "dst"
    src.mkdir()
    dst.mkdir()
    (dst / "f").write_text("x")
    import pytest as _p

    with _p.raises(RuntimeError):
        copy_tree_verified(src, dst)


def test_text_mirror_roundtrip(tmp_data_dir):
    from transstation.core.mirror import cleanup_item_files, text_mirror_path, write_text_mirror
    from transstation.store.db import Item

    p = write_text_mirror(7, "你好镜像")
    assert p.read_text(encoding="utf-8") == "你好镜像"
    assert p == text_mirror_path(7)
    it = Item(kind="text", id=7)
    cleanup_item_files(it)
    assert not p.exists()


def test_image_mirror_paths(tmp_data_dir):
    from transstation.core.mirror import image_mirror_path, thumb_path

    p = image_mirror_path(3)
    assert p.name == "3.png" and p.parent.name == "images"
    t = thumb_path(3)
    assert t.name == "3.png" and t.parent.name == "thumbs"


def test_settings_roundtrip(tmp_data_dir):
    from transstation.store.settings import Settings

    s = Settings(tmp_data_dir / "settings.json")
    assert s.get("hotkey") == "Ctrl+Alt+T"  # 默认值
    s.set("hotkey", "Ctrl+Shift+Q")
    s.set("ignore_apps", ["chrome.exe"])
    s.save()
    s2 = Settings(tmp_data_dir / "settings.json")
    assert s2.get("hotkey") == "Ctrl+Shift+Q"
    assert s2.get("ignore_apps") == ["chrome.exe"]
    # 未知键写入被忽略
    s2.data["__bad"] = 1
    s2.save()
    s3 = Settings(tmp_data_dir / "settings.json")
    assert "__bad" not in s3.data


def test_rel_time(tmp_data_dir):
    from datetime import datetime

    from transstation.core.timefmt import rel_time

    now = datetime(2026, 9, 6, 12, 0, 0)
    assert rel_time(now.isoformat(timespec="seconds"), now) == "刚刚"
    assert rel_time(datetime(2026, 9, 6, 11, 59, 0).isoformat(), now) == "1 分钟前"
    assert rel_time(datetime(2026, 9, 6, 10, 0, 0).isoformat(), now) == "10:00"
    assert rel_time(datetime(2026, 9, 5, 23, 0, 0).isoformat(), now) == "昨天 23:00"
    assert rel_time(datetime(2026, 8, 1, 8, 0, 0).isoformat(), now) == "08-01"
    assert rel_time(datetime(2025, 12, 31, 8, 0, 0).isoformat(), now) == "2025-12-31"
    assert rel_time("") == ""
