【步骤编号】step_28
【上游依赖】logs/step_27.md；main基线b8b5b80fe1b4342af896ff162c1eafbf2b7fda0a。
【做了什么】统一付费/SYSTEM条件契约，登记并统一解析回家等地点别名，将原文操作依据显式传入模型，修复两种真实拒绝。
【产物】11项正式源/测试、新增test_live_action_contract.py、1.9.1成品、开发修订；本步plan/baseline/checks/replay/install/log。
【验收证据】
- V1：baseline记录11父版及12保护源。真实80cdc412时间戳1795106340187是合法主宅移动被输入字面依据拒绝；984026ba时间戳1795107009241的付费conditions空串来自现存提示冲突；不读取无关聊天、不打印密钥。
- V2：6项新增事务（首轮5通过、1项重复提交预期错误；修正后仅该项重验通过）+2项既有收费/重试迟到边界+8项读取审计，共16项通过；Node语法、bridge_interaction/contract/sessions全部通过。验证付费必需七字段、SYSTEM空、别名与明确移动、否定/未来/疑问/多目的地不自动执行、无NPC条件、退款后错误传入重试和租约拒绝。移动事务只改玩家位置，NPC保持，净费用5且重复提交不再写。
- V2真实重放：生产finalMessage处理原移动结果及15项真实工具回执通过；复制当前真实存档的生产preflight接受该原移动JSON和“回到家里，看看妈妈在不在家”。预检使用离线源正文一致回执、未提交剧情；不是新真实模型执行或原租约重放。缺条件的真实旧结果仍在传输层明确拒绝，未猜补语义。
- V2安装：构建ARCHIVE_OK，包SHA256见install；原ID导入1.9.1并恢复start/status，running/enabled=true、busy=false、inFlight=null、pendingResult=false、lastError空，continuous及旧聊天标识保留；sessionReady=false因尚无新任务。Python未重启，未模型/TTS调用。
- V3：11父版逐一核验归档开发者功能/归档/项目清理/历史修改备份/step_28，12保护源与基线相同；旧1.9.0包可原ID回退，未覆盖式演练。
【回滚方式】R1，暂停桥接及Python后在项目根：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_28_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
原ID导入scene_chat_dev/artifacts/故事桥接-continuous-1.9.0.toolpkg并复查状态，不覆盖运行事实、不强推。
【清理与提交】清理本步tmp_step28*及官方PyPI临时依赖，保留fix_wire.py；只暂存本步清单。原data/记忆库真实使用差异、.nomedia和系统trash/图片删除不提交不清理。功能分支提交后main快进拉取/合并/推送，实际SHA以最终工具回执为准。
【验证调用】首轮批次1次，夹具定向复验+真实重放/构建1次，源/父版/保护核验1次，安装状态1次；部署与Git操作另计。实际工作跨读取/交易/桥接多文件，超出默认短任务工具预算；未重复跑已通过检查，未虚构通过。
【下一步】停止重跑Pydroid3的语音运行.py、刷新首页，再原编号重试。当前原行动可按登记别名解析，不需清档或改模型；如模型仍漏字段，具体错误保留，维护端未代点。
【当前】深渊天平正式互动项目 / 条件契约和回家解析修复已安装及离线验收 / 待Python重启与真实新回合验收。
