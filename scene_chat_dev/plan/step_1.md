对象: scene_chat 频繁交流实验分支
授权: 用户已批准 Operit场景交流协议审阅稿并要求开始执行。
目标: 接通独立服务、桥接分发、连续交流页面并安装同ID插件更新。
验收: 源覆盖、事务幂等、租约/版本拒绝、恢复、语法与插件状态；不调用真实模型。
不变量: 原存档、data.json、语音配置与立绘不变；不自动重试生成。
写入范围: scene_chat.py、scene_chat.html、story_service.py、AGENTS.md入口索引、txt文件/提示词.md入口索引、scene_chat_dev开发与产物、开发者说明书与修订日志。
回滚: 同目录备份恢复既有文件；插件导入scene_bridge_original.toolpkg；新增文件可删除。
