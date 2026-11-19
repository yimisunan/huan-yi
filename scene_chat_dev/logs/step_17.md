【步骤编号】step_17
【上游依赖】logs/step_16.md SHA256 f5d0621965f64bb8e1dad845e908c7a31130cfdedad712762e19b5855628b6fc；用户报告正式首页两次判断失败，继续原项目修复。
【做了什么】核实两次原回复均缺operation值；修复正式桥接空操作传输，保留严格拒绝与原请求正式重试，实际安装1.6.1。
【产物】桥接main.js/manifest.json、build.py、新1.6.1安装包、场景交流规范、bridge_interaction.js、开发者说明书与修订日志；step_17基线与checks。
【验收证据】
V1 改前基线：pwd为/storage/emulated/0/互动对话项目/Gemini网页版，realpath为/sdcard/互动对话项目/Gemini网页版；6份父版与13份保护源的大小/mtime/指纹见step_17_baseline.json。写入前桥接1.6.0暂停且空闲，无outbox/inFlight；现役protocol=1已加载。任务原编号live-9709cbd6-f5e4-4bfd-a901-fcb8f3acceaf、开始、attempt2、failed；正式交流0条。原专用会话36abc550-4393-4802-8f65-9b90708d170c的两条最终回复时间戳1795071121710与1795071196559均为operation冒号后直接逗号。观测仅定位到持久化最终消息，不假称已证明提供商原始流或平台剥离原因。
V2 改后结果：
- 正式live_interaction信封、最终提醒、专用角色与权威规则统一空字符串传输；合法JSON解析后只改顶层operation值为null，保留其余原文字节（含需服务端拒绝的重复键）。旧合法null与动作对象兼容；不修补缺值/围栏，不增操作权限，不额外调用模型自动修复。
- node --check通过；node scene_chat_dev/tests/bridge_interaction.js原样LIVE_WIRE_OK与BRIDGE_INTERACTION_OK；node scene_chat_dev/tests/bridge_contract.js五条PASS。直接覆盖两次真实残缺回复重放、空串转换、动作/旧null/重复键/非正式入口保真与缺工具拒绝。
- 首次定向检查发现handoff逗号前缺值未匹配旧诊断，修正该局部后定向重验一次通过。两次终端多行内联命令的字面字符串在传输中变化造成SyntaxError，均改为已落盘脚本运行，不当作程序通过。
- 构建ARCHIVE_OK；归档SHA256 e3738b987d9fb53bdf687aa879053b3a1c0c1b52dabbb4955ba0bd8636e485fa，manifest/main.js/包ID与源码核对，zip完整且无父版或bak。实际plugin import成功，plugin show与story_bridge:status均核实1.6.1、原设备安装位置及启用状态，模型/workspace/chat配置保留。
- 真实验证仅一次原请求retry API，保持原意图/编号/base_revision；按用户已有运行状态恢复桥接。原编号开始的第3次尝试已committed，正式交流1条、明确行动0次；读取审计required_reads_verified=true，回执与消息已落到同一正式事务。刷新/恢复会取得已保存回应。
- 真实最终任务/正式消息/审计路径及结果摘要见step_17_checks.json；未运行真实清档、未发送额外玩家台词、未调用TTS；未手写存档/data。Python服务未修改，无需因本步重启Pydroid。
- 7份修改/新增源与6份父版最终校验；普通交流时三存档、语音配置、关系/事件参数及后端和首页源码均保持。data只允许随正式接受更新。验证预算因真实失败原文重放、一次诊断修正和原请求端到端观察超过单事务4次，未重跑全项目测试或建立新环境。
V3 反向可行：6份父版逐字节核验并移至既有历史修改备份目录，baseline已更新路径；源文件回退单命令如下，不修改运行事实。已安装插件的回退需先暂停桥接、导入既有1.6.0安装包，再核验版本；源码命令不假称覆盖平台部署。未作覆盖式回滚演练。
【回滚方式】R1，暂停桥接后执行：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_17_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
插件回退：operit2 plugin import /virtual/android/documents/230ffdc0fe524442bfde22083d61c969/scene_chat_dev/artifacts/故事桥接-continuous-1.6.0.toolpkg，然后plugin show核验。
【清理】仅清理本步tmp_step17_*，保留既有fix_wire.py；无新测试服务器/依赖。无真实数据删除，旧失败会话保留。
【下一步】用户刷新或点恢复，继续接话；原失败消息已接受，不必再点重试。资源/耗时/恢复/阶段参数沿原待定，不在本修复扩展。
【当前】深渊天平主项目互动改造 / operation空操作传输修复并安装1.6.1，真实原请求最终committed / 完成本次失败修复。
