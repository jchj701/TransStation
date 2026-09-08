"""打包为“单文件便携版”：一个 TransStation.exe 即完整程序，双击即用，
不依赖 Python/系统组件（Win10/11 x64），数据目录自动跟随 exe 所在位置。

用法：python tools/build_portable.py
产物：dist/TransStation/
  TransStation.exe   单文件自包含程序（可单独拷走，数据自动建在 exe 旁）
  data/              用户数据（重建时自动保留，绝不删除）
  README.txt

关键约束：本脚本任何时候都不得删除/覆盖已有 data/ 内容（用户数据）。
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

# CI（pwsh/cp1252 控制台）等非 UTF-8 环境下，中文 print 会 UnicodeEncodeError；
# 统一按 UTF-8 重配置标准流，任何平台都不会因控制台代码页崩溃
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "TransStation"
OUT_DIR = ROOT / "dist" / APP_NAME
DATA_DIR = OUT_DIR / "data"
STASH = ROOT / "build" / ".data_stash"


def main() -> int:
    import PyInstaller.__main__ as pyi

    # 1) 保全用户数据：重建前把 data/ 整体挪到暂存区
    had_data = DATA_DIR.exists()
    if had_data:
        shutil.rmtree(STASH, ignore_errors=True)
        DATA_DIR.rename(STASH)
        print(f"已保全用户数据：{DATA_DIR} → {STASH}")

    # 2) 清空并重打单文件 exe
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    exe_single = ROOT / "dist" / f"{APP_NAME}.exe"
    exe_single.unlink(missing_ok=True)
    args = [
        str(ROOT / "main.pyw"),
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",                       # 单文件：系统解耦、可单独分发
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyi"),
        "--specpath", str(ROOT / "build"),
        "--collect-all", "PySide6.QtSvg",  # 自绘 SVG 图标渲染
    ]
    ico = ROOT / "transstation" / "resources" / "app.ico"
    if ico.exists():
        args += ["--icon", str(ico)]
    print("运行 PyInstaller（单文件模式）…")
    pyi.run(args)

    if not exe_single.exists():
        print("打包失败：未生成 exe", file=sys.stderr)
        if had_data:
            shutil.rmtree(DATA_DIR, ignore_errors=True)
            STASH.rename(DATA_DIR)  # 失败也要把数据放回去
        return 1

    # 3) 组装便携目录：exe + data + 说明
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exe_single.rename(OUT_DIR / f"{APP_NAME}.exe")
    if had_data:
        STASH.rename(DATA_DIR)
    else:
        DATA_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "README.txt").write_text(
        "中转站 TransStation（单文件便携版）\n\n"
        "双击 TransStation.exe 启动，程序驻留系统托盘。\n"
        "默认呼出快捷键：Ctrl+Alt+T（可在设置中修改）。\n\n"
        "数据自动保存在本 exe 所在目录的 data/ 下；\n"
        "把 exe 单独拷到任何 Win10/11 x64 机器双击即可使用，\n"
        "整体拷贝 data/ 即完成备份或迁移。升级版本：替换 exe、保留 data/。\n",
        encoding="utf-8",
    )
    size_mb = OUT_DIR.joinpath(f"{APP_NAME}.exe").stat().st_size / 1e6
    print(f"✔ 单文件便携版已生成：{OUT_DIR / (APP_NAME + '.exe')}（{size_mb:.0f} MB）")
    print(f"  用户数据已保留：{DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
