"""程序根与数据目录解析。

数据目录默认 = 程序根目录下的 data/（便携优先：整体拷贝 data/ 即完成迁移）。
程序根锚点：打包后取 exe 所在目录；开发态取项目根目录（本文件的上两级）。
一律不依赖进程 CWD，避免快捷方式/双击启动导致的路径漂移。

数据目录可通过 <程序根>/.data_dir.json 绑定到其它绝对路径（设置界面迁移后写入）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BOOTSTRAP_NAME = ".data_dir.json"
DEFAULT_SUBDIR_NAME = "data"

# 内存态覆盖（命令行 --data-dir / 测试用）：优先级高于 bootstrap 绑定，不写盘
_override: Path | None = None


def override_data_dir(path: Path | None) -> None:
    """设置/清除运行时数据目录覆盖（仅本次进程生效，不写 .data_dir.json）。"""
    global _override
    _override = Path(path).resolve() if path else None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """程序根：exe(打包) / 项目根(开发)。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bootstrap_file() -> Path:
    return app_root() / _BOOTSTRAP_NAME


def default_data_dir() -> Path:
    return app_root() / DEFAULT_SUBDIR_NAME


def _read_bootstrap() -> str | None:
    try:
        raw = bootstrap_file().read_text(encoding="utf-8")
        data = json.loads(raw)
        p = str(data.get("path", "")).strip()
        return p or None
    except (OSError, ValueError):
        return None


def data_dir() -> Path:
    """当前生效的数据目录：命令行覆盖 > .data_dir.json 绑定 > 程序根 data/。"""
    if _override is not None:
        return _override
    p = _read_bootstrap()
    if p:
        cand = Path(p)
        # 绑定路径失效时（盘符变化/被删除）回落默认目录
        if cand.exists():
            return cand.resolve()
    return default_data_dir()


def set_data_dir(path: Path) -> None:
    """记录数据目录绑定（供迁移使用）。"""
    bootstrap_file().write_text(
        json.dumps({"path": str(path.resolve())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_data_dir_binding() -> None:
    try:
        bootstrap_file().unlink(missing_ok=True)
    except OSError:
        pass


def sub_dirs() -> dict[str, Path]:
    """数据目录下的固定子目录。"""
    root = data_dir()
    return {
        "root": root,
        "db": root / "db",
        "images": root / "images",
        "text": root / "text",
        "backups": root / "backups",
        "logs": root / "logs",
    }


def ensure_dirs() -> dict[str, Path]:
    dirs = sub_dirs()
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs
