# 故事桥接

当前源码维护入口为本目录的 `main.js`、`ui/settings.ui.js`、`tools.js` 和 `manifest.json`；插件 ID 为 `local.story.operit_bridge`，当前版本 **2.1.8**，API 2.0.0。根目录运行 `python scene_chat_dev/build.py` 构建到 `scene_chat_dev/artifacts/`，再在 Operit 同 ID 导入才会更新已安装插件。

正式首页使用 `live_interaction` 路由与唯一 `RoundStore` 事务；`scene_chat` 是保留的独立实验入口。插件内置 Operit 2 原生 Compose DSL 设置界面（`ui/settings.ui.js`，挂载于 Operit 主侧边栏「插件」区与「工具箱」），并与网页端「连接与桥接」面板双端实时联动：可直接切换主模型模式（跟随功能槽 / 故事专属固定模型）、选择副模型功能槽、直接改绑所选 Operit 功能槽模型（`model function-set`）、切换双阶段流式/单阶段精简、副模型思考模式（`auto` 智能自适应 / `off` 常关 / `on` 常开）、会话策略及防漂移切窗轮数（2～30 轮），`/storybridge` 命令继续兼容。

v2 协议（`program_prefix_v2`）由后端 `story_compiler.py` 将全局稳定规则（Zone 0）与当前场景在场人设/关系知情边界（Zone 1）冻结写入专用角色卡的 `characterSetting` 与 `otherContentChat`，仅在 SHA-256 变化时同步一次，每轮 user 仅传极小增量（delta），以最大化隐式前缀 KV 缓存命中；支持基于 `/api/story/worker/wait` 的 Long-Polling 秒级领单，以及通过无状态 `Tools.Chat.call` 独立处理商城「AI 定制询货（`shop-inquiry`）」进货请求而不触碰或重置主剧情会话上下文。默认双阶段模式（`dual_stream_v2`）中，主模型开启思考专注流式微幕剧场演播并通过 `/stream` 推送状态与预热音频，演播结束后由选定的 Operit 2 功能槽（默认 `SUMMARY`）经 `Tools.Chat.call(..., enableThinking)` 无状态完成后台结构化结算（未绑定时自动回退主功能槽；默认 `auto` 智能模式首轮极速免思考，校验未通过原地重试第 2～3 轮时自动启用思考并回传精准错误修复提示，不重跑前台），最终仍由服务端单一 `RoundStore` 事务原子落盘。旧 v1 程序交付路径与实验入口保持兼容。

CommonJS JavaScript 是当前可维护源码；`scene_chat_dev/types/` 保留宿主 API 类型。运行与维护的详细交接见 `../src/新窗口交接.md`。
