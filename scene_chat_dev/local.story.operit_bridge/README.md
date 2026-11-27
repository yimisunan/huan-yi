# 故事桥接

当前源码维护入口为本目录的 `main.js`、`ui/settings.ui.js`、`ui/theater.ui.js`、`tools.js` 和 `manifest.json`；插件 ID 为 `local.story.operit_bridge`，当前版本 **2.3.0**，API 2.0.0。根目录运行 `python scene_chat_dev/build.py` 构建到 `scene_chat_dev/artifacts/`，再在 Operit 同 ID 导入才会更新已安装插件。

**v2.3.0 全链路降本增效与零漂移前缀锁定**：演播专用会话默认净化 Operit 宿主样板（`<workspace_rule_file>`、`AGENTS.md`、文件同步/附件说明，可在高级设置开关，零干扰普通聊天与只读工具）；Zone 1 彻底剥离场外提及与中段动态标志切换，实现同场景 100% 字节级 KV 前缀锁定；Zone 2 真差分与指纹去重、按 `prefs_epoch` 精确触发重卷、以及 `monitor()` Token 缓存与 6s/30s 空闲自适应退避。

**v2.2.0 零角色卡原生自托管架构**：彻底移除对 `com.operit.character_cards` 的外部依赖，改用 Operit 2 原生 `model:chat` 纯会话配合 `Tools.Chat.writeExtension / readExtension`、`registerSystemPromptComposeHook`、`registerToolPromptComposeHook`、`registerToolLifecycleHook`、`registerPromptFinalizeHook` 与 `registerPromptEstimateFinalizeHook` 实现前缀冻结注入、5 个只读文件工具白名单拦截以及外部世界书隔离，永久免疫角色卡插件改版或下架。

**Operit 2 内嵌 WebView 剧场**：新增 `ui/theater.ui.js`（`ComposeDslWebView`），自动挂载于 Operit 主侧边栏「插件」区与「工具箱」中的「深渊天平剧场」，可直接在 Operit 2 App 内部全屏打开本地网页剧场（默认 `http://127.0.0.1:5000`），避免安卓端切屏被杀后台；同时完整保留外部浏览器访问。

正式首页使用 `live_interaction` 路由与唯一 `RoundStore` 事务；`scene_chat` 是保留的独立实验入口。插件内置 Operit 2 原生 Compose DSL 设置界面（`ui/settings.ui.js`）与网页端「连接与桥接」面板双端实时联动：主模型跟随 Operit `CHAT` 功能槽并支持双端一键改绑，副模型可独立选择 `SUMMARY` / `TRANSLATION` / `TITLE_GENERATION` 等任意槽位并配置思考模式（`auto` 智能自适应 / `off` 常关 / `on` 常开），同时支持双阶段流式/单阶段精简切换、会话策略、防漂移切窗轮数（2～30 轮）及 `/storybridge` 命令。主/副模型的无字数上限自定义系统级 Rule 可在剧场「设置 → 阅读与体验」中独立配置。

CommonJS JavaScript 是当前可维护源码；`scene_chat_dev/types/` 保留宿主 API 类型。运行与维护的详细交接见 `../src/新窗口交接.md`。
