"""pytest 公共夹具：数据目录重定向到临时目录（隔离测试，绝不触碰真实数据）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def tmp_data_dir(tmp_path: Path, monkeypatch) -> Path:
    """把 paths.data_dir() 重定向到临时目录（sub_dirs/ensure_dirs 自动跟随）。"""
    import transstation.paths as paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "set_data_dir", lambda p: None)
    monkeypatch.setattr(paths, "default_data_dir", lambda: tmp_path)
    for sub in ("db", "images", "text", "backups", "logs"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def store(tmp_data_dir):
    """独立 Store（临时目录）。"""
    from transstation.store.db import Store

    s = Store(tmp_data_dir / "db" / "test.db")
    yield s
    s.close()


@pytest.fixture()
def settings_obj(tmp_data_dir):
    from transstation.store.settings import Settings

    return Settings(tmp_data_dir / "settings.json")
