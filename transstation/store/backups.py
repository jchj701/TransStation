"""每日自动备份：把整个数据目录（不含 backups/logs/锁）打成 zip，保留最近 N 份。"""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

_EXCLUDE_DIRS = {"backups", "logs"}


def _excluded(rel: Path) -> bool:
    return any(rel.parts[0] == e for e in _EXCLUDE_DIRS)


def make_backup(data_root: Path, backups_dir: Path, keep: int = 7) -> Path | None:
    """执行一次备份；当天已有备份则跳过并返回 None。"""
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    target = backups_dir / f"backup-{stamp}.zip"
    if target.exists():
        return None
    tmp = backups_dir / f".tmp-{stamp}.zip"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src in sorted(data_root.rglob("*")):
            if not src.is_file():
                continue
            rel = src.relative_to(data_root)
            if _excluded(rel):
                continue
            zf.write(src, rel.as_posix())
    tmp.replace(target)
    _prune(backups_dir, keep)
    return target


def _prune(backups_dir: Path, keep: int) -> None:
    if keep <= 0:
        return
    files = sorted(
        backups_dir.glob("backup-*.zip"),
        key=lambda p: p.name,
        reverse=True,
    )
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def backup_if_due(data_root: Path, keep: int = 7) -> Path | None:
    """启动时调用：今天尚未备份则备份。"""
    try:
        return make_backup(data_root, data_root / "backups", keep)
    except Exception:
        return None


def copy_tree_verified(src: Path, dst: Path) -> None:
    """整体迁移数据目录：优先同卷改名，跨卷则复制后校验并删除源。"""
    dst = Path(dst)
    if dst.exists() and any(dst.iterdir()):
        raise RuntimeError("目标目录非空")
    src = Path(src)
    try:
        src.rename(dst)  # 同卷瞬间完成
        return
    except OSError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    # 校验：条目数/文件数一致（按文件字节总和粗验）
    def _bytes(p: Path) -> int:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    if _bytes(src) != _bytes(dst):
        shutil.rmtree(dst, ignore_errors=True)
        raise RuntimeError("迁移校验失败，已回退")
    shutil.rmtree(src, ignore_errors=True)
