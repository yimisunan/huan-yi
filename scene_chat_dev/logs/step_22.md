【步骤编号】step_22
【上游依赖】logs/step_21.md SHA256 b42cf2c8aeb53f17db1a2ff94914ca96503fcbcfeb86766ae2689375ef2f3c79；七项互动玩法授权持续，合并M4/M5。
【做了什么】交付原8场景池的可播随机序幕/统一新档事务，以及受控SVG游戏结算与展开明细。七项需求的开发批次全部完成，真实加载/手机听感仍单列。
【产物】原盲盒/清理器/服务/地点配置、正式HTML/JS/CSS、test_prologue.py与夹具必要适配、计划/开发说明/修订记录、baseline/checks与本交接。桥接1.8.0源码及音色不改。
【验收证据】
- V1：实际根/sdcard/互动对话项目/Gemini网页版；12目标及13保护源一次基线，每个已覆盖源一份父版，写前并发内容核验。真实存档/data/voice/人物关系、模型音色及桥接均未改动；未运行真实清档/盲盒/故事模型/TTS。
- V2：6项序幕用例通过，覆盖原8场景、同ID确定性与幂等、拒绝旧档覆盖、演播门/首A扣5、partial publish及新档序幕失败恢复；最终3项文案与旧新档兼容检查通过。Python解析/Node语法通过，具体命令与退出码在checks。隔离浏览器确认新档无需先输入开始、三节点逐次/末尾选择、行动后先演播再展示SVG、体力100→95、积分+2/经验+1、4个受控图标、明细折叠/展开且无script/onclick注入。减少动态效果静态规则通过；手机尺寸/键盘大字/真实语音未验，不能据浏览器0尺寸声称通过。临时依赖首次MarkupSafe无通用wheel尾缀，改用wheel中纯Python回退后实际通过，未装系统依赖。
- 部署：桥接status真实1.8.0、enabled/running=true、busy=false、inFlight=null、pendingResult=false，原模型gpt-6.1-sol/工作区保持；现役Python互动协议1，需在Pydroid3停止重跑语音运行.py后刷新加载协议3。旧档无需清空；随机序幕仅玩家确认的新档。无真实首轮生成或TTS费用。
- V3：10父版逐字节指纹核验后归档，13保护源不变，12写入源一致；以下R1/R0恢复命令可执行，未做覆盖式回滚演练。
【回滚方式】R1既有源，R0新增测试/修订。先暂停服务，再执行：
```bash
python -c 'from pathlib import Path; import json,shutil; r=Path(".").resolve(); b=json.loads((r/"scene_chat_dev/logs/step_22_baseline.json").read_text()); [shutil.copyfile(r/v["backup"],r/k) for k,v in b["files"].items() if "backup" in v]; [(r/n).unlink(missing_ok=True) for n in b["created"]]'
```
不回写或覆盖实际运行事实；本步不改变平台插件，无插件回退动作。
【清理】隔离8774服务已停止并HTTP/端口确认关闭，浏览器about:blank；本步临时脚本/夹具/依赖删除，保留已有fix_wire.py。step_22本步plan/log配对；历史step_4无plan仅登记，不补造。
【预算与计量】一次L2范围按依赖分组、复用基线及父版；验证含初次依赖定位修正、6项直接测试与后补3项定向/浏览器，超过默认预算的原因是新档恢复事务与前端可观察联调；无全项目测试。跨段未完整统计总工具数，不补造。测试阶段覆盖式故障均只在隔离根。
【下一步】用户在Pydroid3停止并重跑语音运行.py，再刷新正式首页加载互动协议3；沿旧档继续，需体验序幕时由玩家在页面明确确认新档。手机布局/实听与新协议真实模型首轮留待实际使用验收，维护端不替玩家清档或生成测试剧情。
【当前】深渊天平正式互动项目 / M1～M5七点开发及定向隔离验收完成，桥接1.8.0已安装 / 等待本地Python重启加载与实际使用验收。
