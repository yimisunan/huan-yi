# 深渊天平引擎 · 互动叙事项目

Android / Pydroid3 本地互动叙事项目。正式首页支持逐节点演播、自动语音、段末抉择、体力结算、游戏时间、随机序幕及分层记忆。

新窗口维护请先读 [新窗口交接](scene_chat_dev/src/新窗口交接.md)，再读 [AGENTS.md](AGENTS.md)、[维护环境说明](scene_chat_dev/src/维护环境.md) 与 [最新清理验收](scene_chat_dev/logs/step_29.md)。桥接当前为 1.9.5。跑测试用 `bash scene_chat_dev/run_tests.sh`（加 `--fast` 先拷到 /tmp）。

## 运行

在项目目录安装 Flask、requests 和所用语音后端需要的依赖，然后在 Pydroid3 运行 `语音运行.py`，打开 `http://127.0.0.1:5000`。在首页连接面板启动故事桥接。

Fish 语音密钥从环境变量 `FISH_API_KEY` 读取，请在启动进程的环境中设置，不要提交密钥。本地与仓库源码都使用这一方式。

Operit 桥接源码在 `scene_chat_dev/local.story.operit_bridge/`，现用成品为 [故事桥接 1.9.5](scene_chat_dev/artifacts/故事桥接-continuous-1.9.5.toolpkg)。插件 ID 为 `local.story.operit_bridge`；更新插件需构建后同 ID 导入，修改 Python 后需重启 Pydroid3，修改前端后刷新页面。

## 下载和更新

请下载 GitHub **main 分支最新提交**。这次清理已记录追踪文件的删除，最新 main 下载不包含旧演示、旧安装包、修改备份和废弃文件；Git 历史及其他旧分支仍保留旧版本。

首次下载请解压到新目录。**把 ZIP 覆盖解压到旧目录不会删除旧文件**，会留下已清理内容。已有 Git 工作副本可停服务后正常拉取 main；有本地改动时先保留并处理差异，勿使用强制重置或全目录清空。

继续原存档时须保留同一现场的 `data.json`、`存档/`、`voice_config.json`、`.round-runtime/`、存在时的 `.scene-chat/` 和 `语音仓库/`，按需恢复本地密钥环境。运行目录包含正式原文、知情范围、账本和存档代际，不能只复制三份 txt。维护代理不得把这些本地变化顺带提交。

## 收录范围

仓库保留当前源码、权威规则和人物资料、现用图片、初始 `存档/` 模板与音色配置、现役桥接源码与唯一安装包、维护测试和文字验收记录。仓库内的 `data.json` 是空档初始快照，不含测试剧情；首次使用请在页面选择“新游戏”生成序幕。`.round-runtime/`、`.scene-chat/`、游玩后的 `data.json` 变化、凭据、缓存及旧备份不应随源码提交，所以 GitHub 源码快照不等于完整运行备份。

`scene_chat_dev/src/scene_live/` 与 `legacy_visibility.json` 仍被服务引用，需保留。临时目录在执行测试前创建，测试后清空；历史修改备份已按用户要求清除，追踪源从 Git 历史恢复，勿执行旧记录里依赖本地备份的命令。