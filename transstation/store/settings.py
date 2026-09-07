"""设置：JSON 存储于数据目录 data/settings.json，读取时与默认值合并。"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_SETTINGS: dict = {
    # 呼出与窗口
    "hotkey": "Ctrl+Alt+T",
    "popup_offset_x": 18,
    "popup_offset_y": 14,
    "auto_hide": True,          # 存入后自动收起
    "auto_hide_delay_ms": 800,  # 基础延时；含撤销提示的存入会延长到提示消失
    "pin_default": False,       # 呼出时默认钉住
    "remember_geometry": True,  # 记忆面板尺寸与钉住位置
    "panel_width": 460,
    "panel_height": 620,
    # 取用
    "send_auto_paste": False,   # “发送到前台窗口”后自动 Ctrl+V（模拟粘贴，默认关）
    # 记录与隐私
    "ignore_apps": [],          # 不记录来源/去向的应用（进程名，支持 * 通配）
    "text_mirror": False,       # 文本条目镜像为独立 .txt
    # 数据
    "backup_keep": 7,           # 每日备份保留份数
    # 外观
    "reduce_motion": False,     # 跟随系统设置，可手动覆盖
}

# 手动覆盖系统“减少动画”的取值：None=跟随系统
MOTION_SYSTEM = None


class Settings:
    """扁平键值设置；get/set 自动落盘由 save() 显式执行。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in DEFAULT_SETTINGS:
                        self.data[k] = v
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self.path)

    def get(self, key: str):
        return self.data.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value) -> None:
        if key not in DEFAULT_SETTINGS:
            raise KeyError(f"未知设置项: {key}")
        self.data[key] = value
