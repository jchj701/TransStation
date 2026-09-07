# TransStation 中转站

Windows 桌面效率工具：在任意应用中按住内容拖动，按全局快捷键唤出一个跟随鼠标的小面板，
松手即把文件 / 文本 / 链接 / 图片暂存进来；需要时再拖出、双击或复制到目标应用。
窗口默认不常驻，仅以托盘图标驻留后台 —— **不打断当前工作**。

当前为第一阶段实现（呼出—存入—取用闭环），配套《docs/acceptance.md》真机验收清单。

## 快速开始（开发运行）

```bash
pip install -r requirements.txt          # PySide6
python main.pyw                          # 启动（驻留托盘）
python main.pyw --smoke                  # 自动化自检（无窗口，退出码 0 即通过）
```

默认数据目录：**程序根目录下 `data/`**（便携优先；整体拷贝该目录即完成迁移/备份）。
可另存位置：`python main.pyw --data-dir D:\myTransData`，或在设置界面迁移。

## 使用

| 场景 | 操作 |
| --- | --- |
| 存入文件/文字/图片 | 在其它应用按住内容拖动 → 途中按 `Ctrl+Alt+T` → 面板出现在鼠标旁 → 松手存入 |
| 存入剪贴板内容 | 先复制，呼出面板后点剪贴板按钮（或空状态大按钮） |
| 取用 | 呼出面板 → 双击默认打开；按住卡片拖到目标应用；右键复制/复制路径/发送到前台窗口 |
| 整理 | 搜索 / 类型筛选 / 置顶 / 备注 / 修改类型；删除进回收站保留 30 天 |
| 记录 | 自动记录来源与去向、本周使用次数（详情统计在后续版本展开） |

## 便携版（单文件 exe）

`python tools/build_portable.py` 产出 `dist/TransStation/TransStation.exe` ——
**一个自包含 exe**，无 `_internal` 等附带目录、不依赖 Python 或系统组件，任何
Win10/11 x64 双击即用（含首次启动解压，约 2~4 秒）。

- **数据跟随 exe**：在 exe 所在目录自动创建 `data/`；把 exe 拷到任何位置/机器，
  数据就建在那里。升级 = 用新 exe 替换旧 exe、保留 `data/`。
- **重建绝不丢数据**：打包脚本先把 `data/` 移出保全、完成后再放回，可放心反复打包。
- 备份/迁移 = 整体拷贝 `data/`。
- 首次运行建议右键 exe → 发送到桌面快捷方式；如需开机自启（后续版本提供设置项）。

> 发送到前台窗口：默认把内容写入剪贴板并提示手动 Ctrl+V；
> 设置中可开启“发送后自动 Ctrl+V”（模拟粘贴，默认关闭，与需求范围一致）。

## 项目结构

```
main.pyw                   入口（无控制台；--smoke 自检）
transstation/
  paths.py                 程序根 / 数据目录解析（data/ 便携优先，.data_dir.json 可改绑）
  app.py                   装配与编排：托盘、单实例唤醒、热键、全部面板动作
  resources/               tokens 设计令牌 · strings_zh 文案 · icons 自绘线性 SVG · style QSS
  core/                    hotkey 全局热键 · winutil 前台窗口识别 · kinds 内容解析
                           mirror 镜像/缩略图 · dragstate 拖拽检测 · timefmt
  store/                   db.py 全部 SQL · settings.py JSON 设置 · backups.py 每日备份
  olednd/payload.py        拖出负载 / 剪贴板（CF_HDROP / CF_UNICODETEXT / CF_HTML / CF_DIB）
  ui/                      panel 浮窗(拖放目标/浏览) · cards 卡片列表 · toast/dialogs
                           settings_dlg 设置 · recycle_dlg 回收站 · onboarding 引导
tests/                     pytest（纯逻辑层；GUI/真实拖放靠 acceptance.md 人工验收）
tools/build_portable.py    PyInstaller 便携打包
docs/acceptance.md         真机验收清单
```

## 技术要点（为什么这么做）

- **Qt 在 Windows 原生走 OLE**：`acceptDrops` 即注册 OLE 拖放目标，可在其它应用
  （资源管理器/Chrome/微信…）拖拽途中呼出并接收；`QDrag` 拖出携带
  CF_HDROP（文件）/ CF_UNICODETEXT+CF_HTML（文本与链接）/ CF_DIB（位图）。
- **全局热键**用 `RegisterHotKey` + Qt 原生事件过滤，任何应用拖拽中都能触发。
- 拖拽中呼出面板以 `WA_ShowWithoutActivating` 显示，不抢焦点、不打断拖放。
- 文件条目只记路径不复制；位图/剪贴板图片才本地镜像 PNG；文本镜像为开关。
- 链接拖入优先取 CF_HTML 锚文本作标题；整体即 URL 的文本识别为链接。
- 数据 SQLite（WAL）+ 每日自动备份 zip（默认保留 7 份）+ 软删除回收站（30 天）。

## 真机验收

跨应用拖放无法自动化模拟，请按 [docs/acceptance.md](docs/acceptance.md) 逐项真机验证。

## 与 PRD 的差异说明（工程取舍）

1. “存入后自动收起”的生效延时取 `max(设置延时, 2800ms)`，给撤销按钮留出操作时间。
2. “发送到前台窗口”默认 = 剪贴板 + 提示（§9 不做模拟粘贴自动化）；可选自动 Ctrl+V 默认关。
3. 卡片为单列行卡片（含图片缩略图），非多列网格 —— 视觉形态待体验反馈后调整。
4. 失效链接筛选、忽略链接检查、报表、建议行等在后续里程碑（M2–M4）接入；
   数据结构（link_state 等字段/usage_log）已预留。
5. 文本条目超 20 万字符截断存储（防 DB 膨胀，可通过代码常量调整）。

## 数据与隐私

全部数据仅存本机；不上传云端；删除软删 30 天；每日自动备份；规则/报表为本地生成。
