【步骤编号】step_16
【上游依赖】logs/step_15.md SHA256 b22e584e1682d4532bfccb7da6b48d253afe306b4a7556c54e8697f4c6ede989；用户已批准按纠偏计划直接改造正式主HTML、正式存档及规则JSON。
【做了什么】直接替换正式首页为B连续互动；复用StoryService正式会话任务与RoundStore唯一写入器，加入消息/合法行动同事务接受、分页/重启恢复、原编号重试与新档生命周期；同步规则/四库JSON及导出，构建并实际安装桥接1.6.0。
【产物】main_template.html、story_client.js/css、interaction_runtime.py、round_runtime.py、story_service.py、injection_core.py、语音运行.py、存档清理器.py；txt文件/互动运行配置.json与相关规则/四库JSON；22条Operit派生导出；scene_chat_dev/local.story.operit_bridge及artifacts/故事桥接-continuous-1.6.0.toolpkg；tests/test_interaction.py、tests/bridge_interaction.js；开发者说明书/修订日志；step_16基线。未新增演示页。
【验收证据】
V1 改前基线：真实pwd /storage/emulated/0/互动对话项目/Gemini网页版；realpath /sdcard/互动对话项目/Gemini网页版。23份既有文件父版大小/mtime/SHA256与7份只读源指纹见step_16_baseline.json；父版均校验后移入现有历史修改备份目录，基线已更新真实最终路径。
V2 改后结果：
- 正式HTTP入口仍由语音运行.py的/服务main_template.html，首页直接加载story_client.js/css及既有voice_client.js；输入无旧阅读进度门。
- 正式live_interaction沿原/api/story/tasks、worker/claim/preflight/result、显式retry；模型只读本次原文包，按真实文件回执及完整行覆盖核验。语义checks与程序读取事实分开，不能宣称程序证明了因果或意愿。
- 新消息文件.round-runtime/interaction/序号.json与四源/META使用同一prepared/committed日志，恢复白名单与临时物清理已覆盖；data最后发布。同ID去重、过期版本拒绝、存储失败保留validating、恢复不重复执行。
- 支持已登记地点的玩家移动、整组库存交付；不移动其他人物、不新发物、不拆数量。物品状态/接收人/位置写入正式图鉴；非法在场、无库存与重复交付拒绝。条件不足可以返回null操作和待处理说明，保持世界未执行。
- 消息、明确行动与旧回合分开；当前交流不自动执行旧回合监视骰/时效/冷却/任务发放与破局累计。旧完整回合入口保留，保存正式交流计数。当前资源配置pending且成本/恢复/阈值/耗时为null；成本政策的查表预检、资源不足拒绝、事务扣减和重送不重复扣已实现并仅在隔离根试验。恢复/上限未实现，非空配置明确拒绝。
- 新档接口有明确界面确认、版本标识、同ID回执，持RoundStore同锁复用清理器事务并留旧档副本；在途任务阻断。清理范围含正式消息、.scene-chat、任务及读取包；新档标识防止旧标签页输入污染相同初始指纹的新档。模型会话按新档/地点/在场/模型隔离与按累计容量重建，无24次产品边界。
- 运行规则/四库content已适配正式短交流，元数据（名称、关键词、常驻、优先级等）逐项保持；22条导出content与原源一致，关系源及事件注册表未改。未自动覆盖平台世界书配置；正式packet直接读取更新后的原源。
- 全部15项正式测试：PYTHONPATH=scene_chat_dev/tmp/test-deps PYTHONDONTWRITEBYTECODE=1 python scene_chat_dev/tests/test_interaction.py；原样结论“Ran 15 tests in 68.960s / OK”，随后条件不足不执行新增单项“Ran 1 test in 2.336s / OK”。共16项有真实通过观测。测试包含65次交流分页、消息幂等、移动/交付、旧版本、新档标识、完整读取、prepared回退与committed重做、validating恢复、新档API及资源不足/不重复扣减。
- node --check story_client.js及桥接语法通过；node scene_chat_dev/tests/bridge_interaction.js原样“BRIDGE_INTERACTION_OK routes, reminder, role, no automatic memory repair”；构建“ARCHIVE_OK …/故事桥接-continuous-1.6.0.toolpkg”，zip无父版或旧bak。实际Operit plugin import成功，plugin show与story_bridge:status均核验1.6.0、空闲、暂停，现有模型与工作区绑定保留。
- 隔离5091服务直接提供正式主HTML和正式JS/CSS。浏览器验证发送排队→离线固定回执经过正式接受链→旁白/动作/对白同线→发送恢复可用→刷新记录→新档明确确认→0条旧记录，console errors=[]。这是隔离固定回执检查，未调用真实模型或TTS。工具浏览器innerWidth/innerHeight均0，resize返回不支持，未宣称手机视觉验收通过；已停止隔离服务并离开页面。
- 定向完整性输出：25份功能/规则/派生文件、23份父版、7份只读源、22条导出、30个旧读取提取key、1.6.0纯净安装包均核验；最终16项覆盖不同接受故障。初次预检有缩进锚点与缺失.prev新文件判定错误，均在写入前被拦截；初次离线测试缺relationship_query副本、成本用例在移动后误用旧地说话人，修正测试夹具后定向通过；打包遗留1.5.0断言修正后构建通过。
验证调用超过技能单事务4次预算：本步跨正式写入事务、桥接协议、全规则与新档生命周期分组；出现真实失败后定向复验，并新增新档标识/拒绝行动/成本接口检查，未用重复全量项目测试替代交付。未进行真实清档、付费模型或TTS调用。
V3 反向可行：23份父版全部逐字节校验且路径在baseline；下列单命令可恢复源码与删除本步新增源码/交付物，不恢复或写入运行事实；未覆盖演练。已安装插件需同时停用新插件并重新导入既有1.5.0安装包（parent_available=True），再重启本地服务。部署配置回退与源码回退分开说明，不假称一个文件命令可跨平台原子恢复。
【回滚方式】R1 源码父版恢复（先暂停桥接/停止服务）：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_16_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/p).unlink(missing_ok=True) for p in b["created"] if (r/p).is_file()]'
```
插件回退：operit2 plugin import <本工作区VFS路径>/scene_chat_dev/artifacts/故事桥接-scene_chat-1.5.0.toolpkg；然后读取plugin show核验。父版文件与安装包不作为运行规则。
【清理】临时测试依赖、隔离根、浏览器固定回执、修改脚本均于交接后删除，仅保留上游已有tmp/fix_wire.py。备份不留在插件包或根目录。正式运行数据未清空。
【下一步】需在Pydroid停止并重新运行语音运行.py，刷新正式首页/，再启动桥接；本轮不能把源码/离线检查当现役服务已加载。真实模型承接、手机版视觉与TTS链待重启后联调。需要用户裁决：消耗资源种类、每次基础量及移动/交付追加、恢复与上限、实际行动耗时及阶段/旧时效推进单位；秘密披露仍沿既有资格锁，未定义新解锁。
【当前】深渊天平主项目互动改造 / 正式首页及统一接受链、规则JSON和新档源代码已落地、隔离验证通过、桥接1.6.0已安装暂停 / 等待现役服务重启与玩法参数裁决，不扩建独立演示页。
