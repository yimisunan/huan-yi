# step_16 · 正式首页连续互动

目标：直接替换正式 main_template.html 为已选B同席聊天，复用RoundStore与StoryService，将普通交流、合法移动/整组物品交付、消息保存恢复纳入同一正式写入事务；同步权威规则、相关JSON及清理生命周期。

上游：logs/step_15.md（904ef3a计划）；用户已明确批准实施，不另设重复批准门。风险L2，按后端、主页面、规则/派生及交接分组滚动预检与写入。

验收：正式首页可立即输入；已接受消息与状态同事务保存；同ID同内容仅接受一次；过期版本/非法在场/无库存行动拒绝；重开恢复；隔离根初始化后无旧消息；真实读取审计仍完整。没有模型或TTS请求冒充真实联调。

不变量：唯一写入器仍为RoundStore；四源不由维护脚本手填；不执行真实清档；原实验聊天不迁移为正式事实；人物身份/关系保持原源；消息次数不等于旧回合/阶段/日期；未定资源数值保持null并明示未启用，不填0或24；秘密披露不越权；已有模型/语音配置保留。

写入清单：
- 后端：round_runtime.py、story_service.py、injection_core.py、语音运行.py、存档清理器.py；新增interaction_runtime.py及txt文件/互动运行配置.json。
- 主页面：main_template.html、story_client.js、story_client.css（复用已验收B布局及voice_client.js）。
- 桥接：scene_chat_dev/local.story.operit_bridge/main.js、manifest.json、build.py、artifacts/故事桥接-continuous-1.6.0.toolpkg。
- 规则：AGENTS.md、txt文件/场景交流规范.md、提示词.md、全局执行法典.md、一键注入指南.txt、故事检索索引.md、知识库/叙事判断.json、角色类.json、世界观类.json、系统标签类.json；事件注册表仅在发现实际契约需要时改，数值标签不扩权。
- 派生：Operit世界书导出/operit_worldbook_深渊天平.json及.prev（由原源生成）。
- 验收：scene_chat_dev/tests/test_interaction.py、tests/bridge_interaction.js；按真实环境在scene_chat_dev/tmp内执行定向测试。
- 交接：scene_chat_dev/logs/step_16_baseline.json、logs/step_16.md、开发者功能/开发者说明书/开发者说明书.md、开发者功能/修订日志/2026.11/正式首页连续互动.md。

实现边界：正式协议entry_mode=live_interaction沿现有story任务路由；模型只读本次源文资料包，模型结果由程序校验后正式接受。移动和交付使用程序核定的明确操作，模型不得改变参数或声称未执行动作完成。聊天可提出受限单项操作并检查用户原文依据；多项/歧义需澄清。消息原文保留、近期上下文自动分页，旧段可按本任务提供的阅读路径补查，不靠24条硬上限。计时/阶段阈值与资源启用等待用户参数，不阻塞已定义的交流和日常操作。

回退：已有文件每文件一次同目录父版并校验，在baseline登记；同组写入前复核指纹、原子替换；失败前进修复一次，仍失败恢复该组。运行数据不参与源码回退。

验证预算：后端定向事务/恢复/读取/动作检查；前端语法与浏览器真实首页检查；规则JSON/派生一致性；最终父版与只读四源指纹核验。Flask不在维护终端时使用已有可用宿主或隔离依赖，不能判断现役服务缺依赖。临时物仅本项目tmp，收尾删除。
