# 深渊天平引擎 · 互动叙事项目

Android / Pydroid 3 + Operit 2 本地互动叙事项目。正式首页支持双阶段流式微幕演播、逐句点按、自动语音与预取、段末抉择、三档体力结算、游戏时钟、随机序幕及分层记忆。

- **玩家上手**：请直接阅读根目录 [游玩指南.md](游玩指南.md)（依赖安装、Operit 2 `CHAT` + `SUMMARY` 模型配置、操作与排障）。
- **开发与维护**：先读 [开发者说明](开发者功能/开发者说明/README.md)、[AGENTS.md](AGENTS.md)、[新窗口交接](scene_chat_dev/src/新窗口交接.md) 与 [维护环境说明](scene_chat_dev/src/维护环境.md)。当前桥接版本为 **2.3.3**；跑测试用 `bash scene_chat_dev/run_tests.sh`（加 `--fast` 先拷到 `/tmp`）。

## 运行

在项目目录安装 `flask`、`requests`（及所用语音后端依赖），在 Pydroid 3 运行 `语音运行.py`，浏览器打开 `http://127.0.0.1:5000`，在首页「连接与桥接」面板或 Operit 侧边栏「故事桥接」原生设置页管理桥接与主/副模型。

Fish 语音密钥从环境变量 `FISH_API_KEY` 读取，请在启动进程环境中设置，不要提交密钥。

Operit 2 桥接源码在 `scene_chat_dev/local.story.operit_bridge/`，现用成品为 [故事桥接 2.3.3](scene_chat_dev/artifacts/故事桥接-continuous-2.3.3.toolpkg)（插件 ID：`local.story.operit_bridge`）。更新插件须运行 `python3 scene_chat_dev/build.py` 并同 ID 导入；修改 Python 须重启 Pydroid 3；修改前端刷新页面。

## 下载和更新

- **手机端一键同步（推荐，无需 Git）**：先停止 `语音运行.py`，在 Pydroid 3 直接运行根目录 [一键同步GitHub.py](一键同步GitHub.py)。脚本自动按 Git Blob SHA-1 增量对比 `main` 并完成新增/更新/删除，**硬保护**根目录 `.git/` 以及 `data.json`、`存档/`、`voice_config.json`、`.round-runtime/`、`语音仓库/`，且变更前自动备份至 `.sync-backup/`（支持 `--dry-run` 预览、`--rollback` 一键撤销及 `--zip` 离线包同步）。
- **Git / 手动 ZIP**：首次手动下载请解压到新目录（**把 ZIP 覆盖解压到旧目录不会删除旧文件**）。已有 Git 工作副本停服务后 `git pull origin main`；有本地改动时先妥善处理，勿强制重置或清空运行目录。

继续原存档时须成套保留 `data.json`、`存档/`、`voice_config.json`、`.round-runtime/`、存在时的 `.scene-chat/` 和 `语音仓库/`，并恢复本地密钥环境。维护代理不得提交这些本地运行态变化。

## 收录范围与手机图库防扫描

仓库保留当前源码、权威规则与人物设定、现用立绘、初始 `存档/` 模板与音色配置、现役桥接源码与唯一安装包（v2.3.3）、维护测试及精简归档文档。仓库内 `data.json` 为空档初始快照，首次游玩请点首页「新游戏」生成序幕。

`scene_chat_dev/src/scene_live/` 与 `scene_chat_dev/src/legacy_visibility.json` 仍被运行服务引用，不可删除；`scene_chat_dev/.nomedia` 与 `txt文件/image/.nomedia` 已随仓库提供，防止 Android 媒体库误扫 `types/*.d.ts`（会被识别为 `.ts` 视频）与角色立绘污染手机相册。