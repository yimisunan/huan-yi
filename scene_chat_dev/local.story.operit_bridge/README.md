# 故事桥接

当前源码维护入口为本目录的 main.js、tools.js 和 manifest.json；插件 ID 为 local.story.operit_bridge，当前版本 1.9.1，API 2.0.0。根目录运行 `python scene_chat_dev/build.py` 构建到 scene_chat_dev/artifacts/，再在 Operit 同 ID 导入才会更新已安装插件。

正式首页使用 live_interaction 路由和唯一 RoundStore 事务；scene_chat 是保留的独立实验入口。会话默认 continuous 持续沿用，不按字符累计自动换窗。连接面板可改 service_restart（Python服务重新启动后新建）、per_action（每个新行动新建，同编号重试沿用），也可空闲时手动重建；旧聊天保留。模型、工作区、存档改变时隔离会话。

每次行动和重试仍须真实读取本次 packet，旧聊天和失败草稿不替代正式存档。读取不要求返回纯尾空白；真正缺正文时在同任务同租约内补读一次。付费条件契约按预扣 kind 生成并完整校验，移动依据由服务的地点别名解析统一提供。

CommonJS JavaScript 是当前可维护源码；scene_chat_dev/types/ 保留宿主 API 类型。运行与维护的详细交接见 ../src/新窗口交接.md。
