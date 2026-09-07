"""PyInstaller 便携打包：产物为目录版（启动快），整体拷贝即便携。

用法：python tools/build_portable.py
产出：
  dist/TransStation/TransStation.exe    主程序
  dist/TransStation/data/               运行时自动生成（settings.json、db…）
  dist/TransStation/README.txt
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "TransStation"


def main() -> int:
    import PyInstaller.__main__ as pyi

    exe_dir = ROOT / "dist" / APP_NAME
    shutil.rmtree(exe_dir, ignore_errors=True)

    args = [
        str(ROOT / "main.pyw"),
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build" / "pyi"),
        "--specpath", str(ROOT / "build"),
        # PySide6 全量收集（QtSvg 用于自绘 SVG 图标）
        "--collect-all", "PySide6.QtSvg",
    ]
    ico = ROOT / "transstation" / "resources" / "app.ico"
    if ico.exists():
        args += ["--icon", str(ico)]
    print("运行 PyInstaller …")
    pyi.run(args)

    exe = exe_dir / f"{APP_NAME}.exe"
    if not exe.exists():
        print(f"打包失败：未找到输出 {exe}", file=sys.stderr)
        return 1
    (exe_dir / "data").mkdir(exist_ok=True)
    (exe_dir / "README.txt").write_text(
        "中转站 TransStation（便携版）\n\n"
        "双击 TransStation.exe 启动，程序驻留系统托盘。\n"
        "默认全局呼出快捷键：Ctrl+Alt+T（可在设置中修改）。\n\n"
        "数据全部保存在本目录 data/ 下：整体拷贝 data/ 即完成备份或迁移。\n",
        encoding="utf-8",
    )
    print(f"✔ 便携版已生成：{exe_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
