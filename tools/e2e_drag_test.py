"""真机端到端拖放自检：模拟“其它应用拖拽中按热键呼出面板并松手存入”。

用真实鼠标注入（SendInput）驱动：
  1. 一个独立的 Qt 拖拽源窗口（内容=文件或文本，走真实 OLE QDrag）；
  2. 按住左键拖出（OLE 拖拽会话开始）；
  3. 拖拽中注入 Ctrl+Alt+T（模拟用户另一只手按热键）；
  4. 光标移到面板上松手 → 检查面板日志中 dragEnter/drop 与数据库落库。

用法：python tools/e2e_drag_test.py file|text [--dir X]
数据目录/日志在 --dir（默认临时）；面板日志含 dragEnter/drop 明细。
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

user32 = ctypes.windll.user32

_MODS = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10}


def _vk_for(name: str) -> int:
    if name in _MODS:
        return _MODS[name]
    return ord(name.upper())


def key_down(vk: int):
    user32.keybd_event(vk, 0, 0, None)


def key_up(vk: int):
    user32.keybd_event(vk, 0, 2, None)


def chord(keys: list[str], pause: float = 0.04):
    for k in keys:
        key_down(_vk_for(k))
    time.sleep(pause)
    for k in reversed(keys):
        key_up(_vk_for(k))


def mouse_move(x: int, y: int):
    user32.SetCursorPos(x, y)
    time.sleep(0.06)


def mouse_down():
    user32.mouse_event(0x0002, 0, 0, 0, None)  # LEFTDOWN


def mouse_up():
    user32.mouse_event(0x0004, 0, 0, 0, None)  # LEFTUP


def wait_log_contains(log_path: Path, needle: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if needle in log_path.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            pass
        time.sleep(0.2)
    return False


def find_panel_rect(log_path: Path, timeout: float = 8.0):
    """从面板日志解析 show: rect_physical=left,top,right,bottom（最后一次）。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            text = log_path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if "rect_physical=" in line:
                    seg = line.split("rect_physical=", 1)[1].split(" ")[0]
                    last = tuple(int(v) for v in seg.split(","))
            if last:
                return last
        except OSError:
            pass
        time.sleep(0.15)
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload", choices=["file", "text"])
    ap.add_argument("--dir", default=None)
    ap.add_argument("--no-drag", action="store_true", help="不启动拖拽，仅验证热键呼出")
    args = ap.parse_args()

    data_dir = Path(args.dir or tempfile.mkdtemp(prefix="ts_e2e_"))
    log_path = data_dir / "logs" / "transstation.log"

    sample = data_dir / "e2e-drag-file.txt"
    sample.write_text("E2E 拖放测试内容", encoding="utf-8")

    # 用独立快捷键（Ctrl+Shift+U），避免与已在运行的实例抢默认键
    settings = data_dir / "settings.json"
    settings.write_text('{\n  "hotkey": "Ctrl+Shift+U"\n}', encoding="utf-8")
    HOTKEY = ["ctrl", "shift", "u"]

    # 1) 启动应用（真实平台，TRANS_DEBUG 打开拖放日志）
    env = dict(os.environ, TRANS_DEBUG="1")
    app_out = data_dir / "app.out.txt"
    app_proc = subprocess.Popen(
        [sys.executable, str(ROOT / "main.pyw"), "--data-dir", str(data_dir)],
        env=env, cwd=str(ROOT),
        stdout=open(app_out, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    print(f"[e2e] 应用已启动 pid={app_proc.pid} data={data_dir}", flush=True)
    if not wait_log_contains(log_path, "启动完成", 15):
        print("[e2e] 应用启动超时", file=sys.stderr)
        app_proc.kill()
        return 2

    # 2) 启动拖拽源 helper（独立进程，同款 Qt/OLE）
    helper_out = data_dir / "helper.out.txt"
    helper = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "_drag_source.py"), args.payload,
         "--sample", str(sample)],
        cwd=str(ROOT),
        stdout=open(helper_out, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    time.sleep(2.0)

    # 3) 光标到拖拽源中心 → 按下 → 小幅移动（OLE 拖拽会话建立）
    src = (900, 300)          # helper 窗口固定位置 center-ish
    mouse_move(*src)
    time.sleep(0.3)
    if not args.no_drag:
        mouse_down()
        time.sleep(0.15)
        mouse_move(src[0] + 24, src[1])          # 触发拖拽
        time.sleep(0.5)
        print(f"[e2e] 拖拽已启动? cursor=({src[0]+24},{src[1]})", flush=True)
        time.sleep(0.5)
    else:
        print("[e2e] 无拖拽模式：仅测热键呼出", flush=True)

    # 4) 拖拽中注入热键呼出面板
    print("[e2e] 注入 Ctrl+Shift+U", flush=True)
    chord(HOTKEY, pause=0.05)
    rect = find_panel_rect(log_path, timeout=6)
    crashed = app_proc.poll() is not None
    print(f"[e2e] 应用进程存活={not crashed} 退出码={app_proc.poll()}", flush=True)
    if rect is None:
        print("[e2e] 未捕获到面板呼出日志", file=sys.stderr)
        mouse_up()
        helper.kill()
        app_proc.kill()
        return 3
    print(f"[e2e] 面板物理矩形: {rect}", flush=True)
    # 5) 面板出现需 OLE 轮询发现新目标：先小步靠近
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    for i in range(8):
        t = i / 8.0
        mouse_move(int(rect[0] + (cx - rect[0]) * t), int(rect[1] + (cy - rect[1]) * t))
        time.sleep(0.09)
    time.sleep(0.6)
    mouse_up()                                # 松手存入
    time.sleep(1.2)

    # 6) 检查结果
    ok_enter = wait_log_contains(log_path, "dragEnter 接受", 1)
    ok_drop = wait_log_contains(log_path, "drop: files=", 1)
    print(f"[e2e] dragEnter接受={ok_enter} drop日志={ok_drop}", flush=True)
    tail = "\n".join(log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-25:])
    print("---- 应用日志尾部 ----\n" + tail, flush=True)

    helper.kill()
    app_proc.terminate()
    time.sleep(0.5)
    print("---- helper 输出 ----")
    try:
        print(helper_out.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        pass
    print("---- 应用 stderr ----")
    try:
        print(app_out.read_text(encoding="utf-8", errors="ignore")[-2000:])
    except OSError:
        pass
    return 0 if (ok_enter and ok_drop) else 4


if __name__ == "__main__":
    sys.exit(main())
