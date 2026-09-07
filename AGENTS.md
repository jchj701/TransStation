# TransStation 开发协作规范（给 AI 与协作者）

## 提交规范（硬性）
- 本项目为**本地 git 仓库**，无远程。每个“任务变更”完成并自测后必须提交：
  `git add <相关文件>` + `git commit -m "<一句话清晰描述>"`。
- message 用中文，动词开头、说清“改了什么/为什么”，如：
  `修复热键长按导致面板跟手闪烁（去抖+拖拽中保持）`
- 禁止提交：`data/`、`dist/`、`build/`、`__pycache__/`、`*.log`、`.pytest_cache/`、`.zcode/`。
- 用户数据只在 `data/`（程序根或 exe 旁），**永远不允许 git 或打包脚本删除/清理它**。

## 常用命令
```bash
pip install -r requirements.txt -r requirements-dev.txt   # 国内源: -i https://pypi.tuna.tsinghua.edu.cn/simple
python main.pyw                    # 开发运行
python main.pyw --smoke            # 离屏自检（exit 0 = 通过）
python -m pytest tests -q          # 纯逻辑单元测试
python tools/e2e_drag_test.py file # 真机端到端拖放（真实鼠标注入，勿在用户工作时段随意跑）
python tools/visual_preview.py     # 视觉预览（真机弹窗截图用）
python tools/build_portable.py     # 打便携包（单文件 exe + data/，重建自动保留 data）
```

## 架构速览
`transstation/`：app.py 装配编排 · resources(令牌/文案/图标/QSS/调色板) · core(hotkey/winutil/kinds/mirror)
· store(db.py 全部 SQL/settings/backups) · olednd(payload 拖放/剪贴板) · ui(panel/cards/…)
要点：深色系统主题需 force_light_palette；热键靠 RegisterHotKey+原生过滤器（已装）；
面板“等待投放”会话 6s 无活动自动收起；打包单文件 exe，数据跟随 exe 所在目录。

## 环境备忘
- 本机 Python 3.14；PySide6 用清华镜像安装。
- 拖放/热键只能真机验证：单元测试覆盖纯逻辑；e2e 脚本覆盖真实拖放；UI 观感由用户验收。
