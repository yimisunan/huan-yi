【步骤编号】step_27
【上游依赖】logs/step_26.md；基线4708d9161cf3d851fc86030f5c2d2cab8ac0cc7e。
【做了什么】修复尾空行导致完整读取误拒绝、付费重试错误丢失、按资料大小频繁换窗；补读与会话策略由服务和玩家控制。
【产物】13项实际变化的现有源/测试、新增恢复/会话测试、1.9.0成品、开发修订；本步plan/baseline/checks/replay/ui/install/log。bridge_interaction.js无变化，父版删除，不提交无效变更。
【验收证据】
- V1：baseline记录现有源及10项保护源，真实失败来源为两个明确聊天ID。逐项核对平台工具结果与资料包：各12次、2363行全部正文，唯一遗漏第2364尾空白；旧120000字符阈值与资料包累计造成换窗，费用重试未传previous_error。
- V2：Python8项审计+3项格式+7项读取恢复/重试/控制+1项既有取消/迟到边界共19项通过；Node两项语法、两套契约及会话/一次补读断言通过；1.9.0构建ARCHIVE_OK。真实两回执的读取验证离线通过，移除最后正文页仍拒绝；原源已变更，重放明确不测当前源新鲜度/剧情语义/提交，不写事实。UI DOM验证设置/重建请求及状态，fetch拦截未执行真实命令；视口0且不支持resize，手机布局未验收。
- V2安装：1.9.0原ID导入成功并start/status确认running/enabled=true、busy=false、inFlight=null、pendingResult=false、lastError空；实际/storybridge session continuous成功。旧Python尚在运行，controlSupported=null、sessionReady=false符合未加载新会话协议；须重启Python后使用完整新控制，维护端未重启、未执行模型/TTS。
- V3：13变化源各一份父版核验归档开发者功能/归档/项目清理/历史修改备份/step_27，10保护源指纹一致；旧1.8.2包可原ID回退，未覆盖式演练。无变化源不留重复父版。
【回滚方式】R1；暂停桥接及Python后在项目根执行：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_27_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items()]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
原ID导入scene_chat_dev/artifacts/故事桥接-continuous-1.8.2.toolpkg并复查状态；不覆盖运行事实、不强推。
【成本与失败记录】本步超出技能默认调用预算：两次真实失败交叉核验、重试/会话跨端修改、Flask依赖缺失与共享存储不支持symlink、夹具与工具字面量异常纠正、浏览器能力限制带来额外定位。没有重复运行已通过的Python测试；最终启动/状态微调后重验受影响Node与重建成品，失败历史保留。用户明确维修/会话控制及既有推main授权持续有效。
【清理与提交】仅清理本步tmp_step27*及依赖，保留fix_wire.py；仅暂存本步明确源/测试/成品/记录，.nomedia、系统trash及他方图片删除保持。功能分支提交、main快进拉取/合并/推送，SHA以最终工具回执为准。
【发现未处理】既有step_4计划/交接配对缺项，未补造；两份失败草稿可能还含后续语义校验问题，本次未接受或重写其剧情，实际新回合仍待验证。
【下一步】Pydroid3停止重跑语音运行.py，刷新首页，在连接与桥接选择会话方式；默认持续沿用，手动点原行动重试。新窗口携本次正式资料，失败草稿不是事实，无需清档。
【当前】深渊天平正式互动项目 / 尾空行与会话控制修复已安装并定向通过 / 待Python重启与真实新回合验收。
