【步骤编号】step_26
【上游依赖】logs/step_25.md；main基线6c6e174e95a5382b3ae3d2f082c6ba8f83c98ed2。
【做了什么】修复正式互动角色与服务读取工具许可不一致、平台字符串行号误拒绝，并规划完整正文分页。
【产物】7项正式源、审计测试、1.8.2成品、开发修订；plan及baseline/checks/install/log记录。
【验收证据】
- V1：step_26_baseline.json记录7源父版、13保护源；失败会话ddc06518实际调用grep_code读取本任务live.txt，服务verify在工具名处拒绝。
- V2：node --check、bridge_interaction、bridge_contract全部通过；生产verify隔离测试8项与packet格式3项全部通过；构建ARCHIVE_OK。测试夹具audit缺键修正一次并仅重验失败测试文件，首次错误保留在checks记录。真实2364行packet规划12段，最大9000字符/22611字节。1.8.2原ID导入成功；start后status为running/enabled=true、busy=false、inFlight=null、pendingResult=false、lastError空。检查、构建、安装和真实分页观测分别记录，不把隔离验证等同实际生成。
- V3：7个父版核验后归档开发者功能/归档/项目清理/历史修改备份/step_26；13保护源SHA256与基线一致。旧1.8.1包保留，未做覆盖式回滚演练。
【回滚方式】R1；暂停桥接及Python后在项目根执行：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_26_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
插件如需回退，原ID导入scene_chat_dev/artifacts/故事桥接-continuous-1.8.1.toolpkg，再复查状态。不覆盖运行事实、不强推。
【清理与提交】只删除本步tmp_step26_start/edit/finish.py，保留既有fix_wire.py；只暂存明确源/交付/记录清单，其他.nomedia/图片删除/trash不处理。功能分支提交后按main规则快进拉取、合并并推送；实际SHA与推送成功以最终工具回执为准。
【验证调用口径】首轮批次1次；测试夹具定向复验及Python语法1次；真实packet分页/保护指纹及父版1次；安装后状态1次。未重复已通过的Node/格式/构建测试；归档与Git检查另记录为交付操作。
【下一步】Pydroid3停止重跑语音运行.py，刷新正式首页，手动“重试本次推演”；新后端与桥接一起生效，无需清档。维护端未代执行付费模型调用或TTS。
【当前】深渊天平正式互动项目 / 读取审计修复已安装、定向验证通过 / 待Python重启及用户原行动实际重试。
